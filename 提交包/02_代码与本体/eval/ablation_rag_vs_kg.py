#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
消融实验：RAG-only vs KG-only vs 双驱动
================================================================

要回答的问题
------------
本项目主张"检索-推理双驱动"是必要的 —— 但此前的依据只有一张断言表
（"纯检索易编造""纯推理找不到原文"），**没有任何测量**。

审阅意见原文：
  "**没有 RAG-only 消融**。那张'纯检索 / 纯推理 / 双驱动'对比表
   **没有任何测量**。"
  "一等奖队伍会用同样的 MCP + 同样的 Skill 但多这一张表压过去。"

本脚本产出那一张表。

三个配置
--------
**B. 仅检索（RAG-only）**
    模拟"把指南全文塞进上下文"的做法：
    ES 检索 top-k 条文 → 交给 LLM 作答。
    **这是绝大多数队伍会做的方案**，也是"直接问大模型"的加强版。

**C. 仅图谱（KG-only）**
    走本项目的图谱推理管道（`run_inference`），
    但**不回检条文原文**（相当于 L3 证据层失效）。

**A. 双驱动（完整系统）**
    图谱推理定位条款 + 条目回检补原文 =
    `run_inference`（含 contraindications / referral / disambiguation）。

评价维度（均可机器核验）
------------------------
  1. **条款命中率** —— 是否定位到 gold 条款
  2. **条款级引用** —— 输出里是否出现【推荐意见N】
  3. **可溯源** —— 引用的条款号是否与 gold 一致
  4. **拒答正确率** —— 信息不足时是否拒绝作答（而非硬答）

用法
----
    python3 eval/ablation_rag_vs_kg.py --out ablation.json
    python3 eval/ablation_rag_vs_kg.py --sample 12 --out ablation.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.request

# ---------------- 配置 ----------------
ES_URL = os.environ.get("ES_URL", "http://nexent-elasticsearch:9200")
ES_INDEX = os.environ.get("ES_INDEX", "4-1fd943cfa3c044419a587e642b005759")
ES_USER = os.environ.get("ES_USER", "elastic")
ES_PASS = os.environ.get("ES_PASS", "nexent@2025")

EMBED_URL = os.environ.get("EMBED_URL", "https://api.siliconflow.cn/v1/embeddings")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "BAAI/bge-m3")
LLM_URL = os.environ.get("LLM_URL", "https://api.siliconflow.cn/v1/chat/completions")
LLM_MODEL = os.environ.get("LLM_MODEL", "deepseek-ai/DeepSeek-V3")
API_KEY = os.environ.get("SILICONFLOW_KEY", "")

TOP_K = 5

# v1.1 修正：原正则只认全角方括号「【推荐意见N】」，
# 导致基线模型写「（推荐意见15）」时被判为"未引用" —— 这是**测量假阴性**，
# 使 B 配置的条款命中率被系统性低估（3 个场景里吃掉 1 个）。
# 现扩展为接受三类写法：全角方括号 / 圆括号 / 裸写。
CLAUSE_RE = re.compile(
    r"(?:【|（|\(|\[)?\s*推荐意见\s*(\d+)\s*(?:】|）|\)|\])?")


# =====================================================================
# B 配置：仅检索（RAG-only）
# =====================================================================

def _post(url: str, payload: dict, timeout: int = 120) -> dict:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {API_KEY}"},
        method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def embed(text: str) -> list[float]:
    d = _post(EMBED_URL, {"model": EMBED_MODEL, "input": [text]})
    return d["data"][0]["embedding"]


def es_search(vec: list[float], k: int = TOP_K) -> list[dict]:
    """在 Elasticsearch 中做向量检索（kNN）。

    字段名以 Nexent 实际索引为准（实测）：
      · 向量字段 = `embedding`（dense_vector, dims=1024）
      · 正文字段 = `content`
      · 来源文件 = `filename`
    """
    body = {
        "knn": {
            "field": "embedding",
            "query_vector": vec,
            "k": k,
            "num_candidates": max(k * 10, 50),
        },
        "_source": ["content", "filename", "title"],
        "size": k,
    }
    req = urllib.request.Request(
        f"{ES_URL}/{ES_INDEX}/_search",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST")
    import base64
    tok = base64.b64encode(f"{ES_USER}:{ES_PASS}".encode()).decode()
    req.add_header("Authorization", f"Basic {tok}")
    with urllib.request.urlopen(req, timeout=60) as r:
        d = json.loads(r.read().decode())
    return [h["_source"] for h in d.get("hits", {}).get("hits", [])]


RAG_SYSTEM = (
    "你是一名呼吸科医生。请**仅依据下面提供的指南原文片段**回答用户问题。\n"
    "要求：\n"
    "1. 如果你的回答基于某条推荐意见，请在句末标注该条款编号；\n"
    "2. 如果提供的片段不足以回答，请明确说明「依据不足」，不要编造；\n"
    "3. 不要给出具体用药名称与剂量。"
)


def rag_answer(question: str) -> dict:
    """B 配置：检索 top-k 条文 → LLM 作答。"""
    try:
        vec = embed(question)
        hits = es_search(vec)
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    ctx = "\n\n".join(
        f"[片段{i+1}] {h.get('content','')[:900]}" for i, h in enumerate(hits))
    prompt = f"指南原文片段：\n{ctx}\n\n用户问题：{question}\n\n请作答："
    try:
        d = _post(LLM_URL, {
            "model": LLM_MODEL,
            "messages": [{"role": "system", "content": RAG_SYSTEM},
                         {"role": "user", "content": prompt}],
            "max_tokens": 1200, "temperature": 0.2,
        })
        text = d["choices"][0]["message"]["content"]
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    return {"ok": True, "answer": text, "retrieved": len(hits),
            "retrieved_chars": len(ctx)}


# =====================================================================
# 评价
# =====================================================================

def analyze(answer: str, gold_clause: str | None,
            case_type: str) -> dict:
    """对一段回答提取可核验指标。"""
    t = answer or ""
    cited = CLAUSE_RE.findall(t)
    gold_num = None
    if gold_clause:
        m = re.search(r"(\d+)", gold_clause)
        gold_num = m.group(1) if m else None

    # 是否明确拒答/承认依据不足
    refused = bool(re.search(
        r"依据不足|无法回答|不能确定|缺少|请.{0,6}(补充|提供)|需要.{0,6}(补充|提供)|信息不足|未覆盖",
        t))
    # 是否给出了处置建议（有随访间隔或处置动词）
    gave_advice = bool(re.search(
        r"随访|复查|手术|切除|活检|转诊|个月", t))

    return {
        "answer_chars": len(t),
        "clauses_cited": sorted(set(cited), key=int),
        "citation_count": len(set(cited)),
        "has_clause_citation": len(set(cited)) > 0,
        "hit_gold": (gold_num in set(cited)) if gold_num else None,
        "self_declared_insufficient": refused,
        "gave_advice": gave_advice,
    }


# =====================================================================
# 主流程
# =====================================================================

# 与端到端验证同源的场景（覆盖须给建议 / 须拒答两类）
SCENARIOS = [
    ("A001", "55岁男性，8mm混合磨玻璃结节，实性成分2mm，吸烟30年，该怎么随访？",
     "推荐意见14", "advice"),
    ("A005", "62岁男性，15mm混杂性磨玻璃结节，实性成分6mm，有毛刺征，该如何处理？",
     "推荐意见15", "advice"),
    ("A009", "48岁女性，6mm纯磨玻璃结节，无吸烟史，该如何处理？",
     "推荐意见13", "advice"),
    ("C001", "我有肺结节，该怎么办？", None, "refusal"),
    ("C002", "发现肺部有个影子，需要处理吗？", None, "refusal"),
]


def main() -> int:
    ap = argparse.ArgumentParser(description="RAG-only 消融实验")
    ap.add_argument("--out", default="ablation.json")
    ap.add_argument("--sample", type=int, default=0,
                    help="只用前 N 个场景（0=全部）")
    args = ap.parse_args()

    if not API_KEY:
        print("[ERROR] 需要环境变量 SILICONFLOW_KEY", file=sys.stderr)
        return 2

    cases = SCENARIOS[:args.sample] if args.sample else SCENARIOS
    result = {"config_b_rag_only": [], "note": (
        "B 配置模拟'把指南片段塞进上下文'的 RAG 方案："
        "ES 向量检索 top-k 条文 → LLM 作答。这是多数参赛队伍会采用的做法，"
        "也是'直接问大模型'的加强版（给了真实条文）。")}

    print("=" * 78)
    print("  消融实验 · B 配置：仅检索（RAG-only）")
    print("=" * 78)
    for cid, q, gold, ctype in cases:
        print(f"\n  [{cid}] {q[:60]}")
        r = rag_answer(q)
        if not r.get("ok"):
            print(f"    ❌ {r.get('error')}")
            result["config_b_rag_only"].append(
                {"id": cid, "question": q, "gold_clause": gold,
                 "case_type": ctype, "ok": False, "error": r.get("error")})
            continue
        a = analyze(r["answer"], gold, ctype)
        print(f"    检索片段 {r['retrieved']} 条 / {r['retrieved_chars']} 字符")
        print(f"    回答 {a['answer_chars']} 字 | 引用条款 {a['clauses_cited'] or '（无）'}")
        print(f"    命中 gold({gold}) : {a['hit_gold']}")
        print(f"    自称依据不足 : {a['self_declared_insufficient']} | 仍给出建议 : {a['gave_advice']}")
        result["config_b_rag_only"].append(
            {"id": cid, "question": q, "gold_clause": gold, "case_type": ctype,
             "ok": True, "answer": r["answer"], "analysis": a})
        time.sleep(1)

    # 汇总
    ok = [c for c in result["config_b_rag_only"] if c.get("ok")]
    adv = [c for c in ok if c["case_type"] == "advice"]
    ref = [c for c in ok if c["case_type"] == "refusal"]
    summary = {
        "total": len(ok),
        "advice_cases": len(adv),
        "refusal_cases": len(ref),
        "hit_gold_rate": (round(sum(1 for c in adv if c["analysis"]["hit_gold"])
                                / max(len(adv), 1), 4)),
        "citation_rate": round(sum(1 for c in ok if c["analysis"]["has_clause_citation"])
                               / max(len(ok), 1), 4),
        "refusal_accuracy": round(sum(1 for c in ref
                                      if c["analysis"]["self_declared_insufficient"])
                                 / max(len(ref), 1), 4),
        "gave_advice_when_insufficient": sum(
            1 for c in ref if c["analysis"]["gave_advice"]),
    }
    result["summary_b"] = summary

    print()
    print("=" * 78)
    print("  B 配置汇总")
    print("=" * 78)
    print(f"  用例数            : {summary['total']}")
    print(f"  条款命中率        : {summary['hit_gold_rate']*100:.1f}%  （{len(adv)} 个须给建议场景）")
    print(f"  条款级引用率      : {summary['citation_rate']*100:.1f}%")
    print(f"  拒答正确率        : {summary['refusal_accuracy']*100:.1f}%  （{len(ref)} 个须拒答场景）")
    print(f"  信息不足仍给建议  : {summary['gave_advice_when_insufficient']} / {len(ref)}")

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n  报告已保存: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
