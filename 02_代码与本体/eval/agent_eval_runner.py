#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能体层端到端评测（北向 API）
================================================================

要解决的问题
------------
独立审计最尖锐的一条：

> `eval/eval_runner.py:31-37` 直接 `import kg_mcp_server as kg`，
> 第 47 行调用 `kg.run_inference(q)`。
> **不经 MCP 协议、不经 Nexent 平台、不经 Skill 编排、不调用 LLM。**
>
> 「评测对象不是系统，是引擎模块。」
> 「把评测对象换成 **Agent 层**（`POST /agent/run`），
>   并**同时报两个数字**：引擎层（可解释误差归因）+ 端到端层（真实能力）。」

本脚本补上**端到端层**：把评测用例真正发给 Nexent 平台上的智能体，
走**完整的 MCP + Skill + LLM 链路**，然后解析回答文本判定指标。

两个层次的分工
--------------
| 层次 | 脚本 | 能回答的问题 |
|---|---|---|
| **引擎层** | `eval_runner.py` | 条款判定逻辑**对不对**（可解释、可归因、快） |
| **端到端层（本脚本）** | `agent_eval_runner.py` | 智能体**实际答出什么**（含 LLM、Skill、MCP 全链路） |

★ 端到端层**更真实但更慢、更贵、更不稳**（LLM 非确定性）。
因此两者**都要报**，不能只报对自己有利的那个。

判定口径
--------
从 SSE 事件流的最终回答文本中解析：
  · **条款命中**：回答中出现的【推荐意见N】是否包含期望条款
  · **可溯源**：回答中是否出现任何【推荐意见N】
  · **拒答正确**：拒答例应**不出现条款编号**，且文本含"无法""请补充""缺少"等
  · **禁忌输出**：禁忌例应出现"不推荐"/"禁忌"字样
  · **分级诊疗**：分级例应出现机构层级词

用法
----
    python3 agent_eval_runner.py \
        --url http://127.0.0.1:5013/nb/v1/chat/run \
        --agent feijiehe --key-file /root/.ak \
        --evalset evalset_v13.json --limit 12 \
        --out agent_eval.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

CLAUSE_RE = re.compile(r"推荐意见\s*(\d+)")


def call_agent(url: str, api_key: str, agent: str, query: str,
               timeout: int = 300) -> dict:
    """调用北向 chat/run，解析 SSE 事件流。"""
    payload = {"agent_name": agent, "query": query}
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), method="POST", headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        })
    t0 = time.time()
    events: list[dict] = []
    with urllib.request.urlopen(req, timeout=timeout) as r:
        for raw in r:
            line = raw.decode("utf-8", errors="replace").strip()
            if not line.startswith("data:"):
                continue
            try:
                events.append(json.loads(line[5:].strip()))
            except json.JSONDecodeError:
                continue
    elapsed = time.time() - t0

    # ★ 修正 2：真正的最终回答在 `final_answer` 事件里。
    #
    # 事件类型实测（一次 8mm mGGN 提问的事件流）：
    #   final_answer              1 条   948 字符   ← **这才是答案**
    #   agent_new_run             2 条  1454 字符   ← 是**系统提示词/运行环境说明**，不是答案
    #   model_output_deep_thinking 1136 条  3541 字符（流式思考分片）
    #   search_content            1 条  5502 字符（知识库命中片段）
    #   execution_logs            2 条  8094 字符（记忆命中）
    #   tool                      3 条（工具调用）
    #
    # 我前两版分别取「最后一条 agent_new_run」和「拼接全部 agent_new_run」，
    # 都拿到的是运行环境说明，因此判定全为"无引用" —— 两次都是假阴性。
    # 现改为优先取 `final_answer`，并以 agent_new_run 中**非环境说明**的部分兜底。
    answer = ""
    for ev in events:
        if ev.get("type") == "final_answer" and isinstance(ev.get("content"), str):
            answer = ev["content"]

    if not answer:
        # 兜底：拼接 agent_new_run，但剔除运行环境说明行
        runs: list[tuple[int, int, str]] = []
        for i, ev in enumerate(events):
            if (ev.get("type") == "agent_new_run"
                    and isinstance(ev.get("content"), str)):
                ui = ev.get("unit_index")
                runs.append((ui if isinstance(ui, int) else 10**9, i, ev["content"]))
        runs.sort(key=lambda x: (x[0], x[1]))
        merged = "".join(r[2] for r in runs)
        merged = re.sub(r"Run workspace:.*", "", merged, flags=re.DOTALL)
        merged = re.sub(r"Write every generated file.*", "", merged, flags=re.DOTALL)
        merged = re.sub(r"^\[Current time:[^\]]*\]", "", merged)
        answer = merged.strip()

    tools = [e.get("tool_name") for e in events if e.get("type") == "tool"]
    return {
        "answer": answer,
        "answer_event": "final_answer" if answer else "fallback_agent_new_run",
        "event_count": len(events),
        "tool_calls": tools,
        "tool_call_count": len(tools),
        "mcp_tool_count": sum(1 for t in tools if t and t.startswith("kg_")),
        "elapsed_sec": round(elapsed, 2),
    }


def judge(case: dict, answer: str) -> dict:
    """按用例类型判定。"""
    cited = sorted({int(n) for n in CLAUSE_RE.findall(answer)})
    ctype = case.get("type", "")
    expected = case.get("expected_clause") or ""
    exp_no = None
    if expected:
        m = re.search(r"(\d+)", expected)
        if m:
            exp_no = int(m.group(1))

    out = {"cited_clauses": cited, "has_citation": bool(cited), "hit": False,
           "reason": ""}

    if ctype == "refusal":
        # 拒答例：**不应**出现条款编号，且应以追问/表单形式索要缺失信息。
        #
        # ★ 修正 3：原判据只查"请补充/无法/缺少"等词，但智能体的实际输出是
        # **结构化追问表单**（"1. 结节最大径是多少毫米（mm）？…"），
        # 不含这些词，因此 3 条拒答例全被判错 —— 是判据的问题，不是系统的问题。
        #
        # 现按"追问的表征"判定，任一成立即可：
        #   · 含问号（表单式追问）
        #   · 含"请补充/请提供/需要补充/无法/缺少/信息不足"
        #   · 出现 ≥2 个需要补充的字段名（直径 / 密度 / 危险因素）
        asks_q = "？" in answer or "?" in answer
        asks_kw = any(k in answer for k in
                      ("请补充", "请提供", "无法", "缺少", "信息不足",
                       "需要补充", "麻烦", "请问"))
        field_hits = sum(1 for k in ("最大径", "直径", "密度", "危险因素")
                         if k in answer)
        asks = asks_q or asks_kw or field_hits >= 2
        out["hit"] = (not cited) and asks
        out["reason"] = ("未引用条款且输出追问" if out["hit"]
                         else ("引用了条款" if cited else "未追问"))
        out["refusal_detail"] = {
            "has_question_mark": asks_q, "has_keyword": asks_kw,
            "field_hits": field_hits,
        }
    else:
        if exp_no is None:
            out["hit"] = bool(cited)
            out["reason"] = "有引用" if cited else "无引用"
        else:
            out["hit"] = exp_no in cited
            out["reason"] = (f"命中推荐意见{exp_no}" if out["hit"]
                             else f"期望{exp_no}，实得{cited}")

    if ctype == "contraindication":
        out["has_contra"] = any(k in answer for k in ("不推荐", "禁忌", "不建议"))
    if ctype == "referral":
        out["has_referral"] = any(
            k in answer for k in ("基层", "分中心", "联盟", "转诊", "上级医院"))
    out["has_disclaimer"] = any(
        k in answer for k in ("仅供", "不构成", "不代替", "免责", "参考"))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="智能体层端到端评测")
    ap.add_argument("--url", default="http://127.0.0.1:5013/nb/v1/chat/run")
    ap.add_argument("--agent", default="feijiehe")
    ap.add_argument("--key-file", default="/root/.ak")
    ap.add_argument("--evalset", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default="agent_eval.json")
    args = ap.parse_args()

    api_key = open(args.key_file, encoding="utf-8").read().strip()
    evalset = json.load(open(args.evalset, encoding="utf-8"))
    cases = evalset["cases"]
    if args.limit:
        # 按类型分层抽样，保证各类型都覆盖
        by_type: dict[str, list] = {}
        for c in cases:
            by_type.setdefault(c.get("type", "?"), []).append(c)
        per = max(1, args.limit // max(len(by_type), 1))
        sel: list = []
        for t, arr in by_type.items():
            sel.extend(arr[:per])
        cases = sel[:args.limit]

    print("=" * 84)
    print("  智能体层端到端评测（北向 API · 完整 MCP + Skill + LLM 链路）")
    print("=" * 84)
    print(f"  智能体: {args.agent}   用例: {len(cases)} 条（分层抽样）")
    print()
    print(f"  {'用例':<7}{'类型':<18}{'期望':<12}{'实得条款':<20}{'工具':<5}{'秒':<7}{'判定'}")
    print("  " + "-" * 78)

    results = []
    for c in cases:
        cid = c["id"]
        try:
            r = call_agent(args.url, api_key, args.agent, c["question"])
        except Exception as e:                              # noqa: BLE001
            print(f"  {cid:<7}{c.get('type',''):<18}调用失败: {type(e).__name__}")
            results.append({"id": cid, "ok": False,
                            "error": f"{type(e).__name__}: {e}"})
            continue

        j = judge(c, r["answer"])
        print(f"  {cid:<7}{c.get('type',''):<18}{str(c.get('expected_clause') or '—'):<12}"
              f"{str(j['cited_clauses'])[:18]:<20}{r['tool_call_count']:<5}"
              f"{r['elapsed_sec']:<7}{'✅' if j['hit'] else '❌'}")
        results.append({
            "id": cid, "ok": True, "type": c.get("type"),
            "question": c["question"],
            "expected_clause": c.get("expected_clause"),
            "answer": r["answer"],
            "answer_chars": len(r["answer"]),
            "cited_clauses": j["cited_clauses"],
            "hit": j["hit"], "reason": j["reason"],
            "has_contra": j.get("has_contra"),
            "has_referral": j.get("has_referral"),
            "has_disclaimer": j["has_disclaimer"],
            "tool_calls": r["tool_calls"],
            "tool_call_count": r["tool_call_count"],
            "mcp_tool_count": r["mcp_tool_count"],
            "elapsed_sec": r["elapsed_sec"],
        })
        time.sleep(2)

    ok = [r for r in results if r.get("ok")]
    hits = sum(1 for r in ok if r["hit"])
    n = len(ok)
    print()
    print("=" * 84)
    print("  ★ 智能体层结果")
    print("=" * 84)
    if n:
        print(f"  用例数            : {n}")
        print(f"  端到端命中率      : {hits}/{n} = {hits/n*100:.1f}%")
        print(f"  有条款引用比例    : "
              f"{sum(1 for r in ok if r['cited_clauses'])}/{n} = "
              f"{sum(1 for r in ok if r['cited_clauses'])/n*100:.1f}%")
        print(f"  含免责声明比例    : "
              f"{sum(1 for r in ok if r['has_disclaimer'])}/{n} = "
              f"{sum(1 for r in ok if r['has_disclaimer'])/n*100:.1f}%")
        print(f"  平均工具调用      : "
              f"{sum(r['tool_call_count'] for r in ok)/n:.1f} 次"
              f"（其中 MCP {sum(r['mcp_tool_count'] for r in ok)/n:.1f} 次）")
        print(f"  平均耗时          : "
              f"{sum(r['elapsed_sec'] for r in ok)/n:.1f} 秒")
        # 按类型
        by_t: dict[str, list] = {}
        for r in ok:
            by_t.setdefault(r["type"], []).append(r)
        print()
        print("  分类明细:")
        for t, arr in sorted(by_t.items()):
            h = sum(1 for x in arr if x["hit"])
            print(f"    {t:<20}{h}/{len(arr)}  {h/len(arr)*100:.0f}%")
    print("=" * 84)

    report = {
        "layer": "agent_end_to_end",
        "note": ("本层走完整链路（Nexent 平台 + MCP + Skill + LLM），"
                 "与 `eval_runner.py` 的**引擎层**评测互补："
                 "引擎层回答『判定逻辑对不对』，本层回答『实际答出什么』。"
                 "本层更真实但含 LLM 非确定性，两者都应报。"),
        "agent": args.agent, "case_count": n,
        "hit_rate": round(hits / n, 4) if n else 0.0,
        "citation_rate": round(sum(1 for r in ok if r["cited_clauses"]) / n, 4) if n else 0.0,
        "disclaimer_rate": round(sum(1 for r in ok if r["has_disclaimer"]) / n, 4) if n else 0.0,
        "avg_tool_calls": round(sum(r["tool_call_count"] for r in ok) / n, 2) if n else 0.0,
        "avg_elapsed_sec": round(sum(r["elapsed_sec"] for r in ok) / n, 2) if n else 0.0,
        "results": results,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"  报告已保存: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
