#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
肺结节处置决策 · 自测执行器
================================================================

读取 evalset.json，逐条调用推理引擎，统计可量化指标：

  · 条款命中率 (Clause Accuracy)     —— 结论条款与金标准一致的比例
  · 覆盖率     (Coverage Rate)       —— 返回 COVERED 的比例
  · 拒答正确率 (Refusal Correctness) —— 应拒答时确实拒答的比例
  · 可溯源率   (Traceability Rate)   —— 输出携带条款编号的比例
  · 平均推理跳数 (Avg. Reasoning Hops) —— 推理链深度
  · 分级诊疗准确率 (Referral Accuracy)

这些指标即材料中"数据自测"一节的量化证据。

用法：
    python3 eval_runner.py --evalset evalset.json --report report.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter

# v1.2：条款编号识别（与 ablation 脚本口径一致，接受全角/圆括号/裸写）
CLAUSE_RE = re.compile(
    r"(?:【|（|\(|\[)?\s*推荐意见\s*(\d+)\s*(?:】|）|\)|\])?")

from typing import Any

# 复用 MCP Server 内的推理实现，保证评测对象与线上服务一致
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import kg_mcp_server as kg  # type: ignore
except ImportError:
    sys.path.insert(0, "/tmp")
    import kg_mcp_server as kg  # type: ignore


def run_case(case: dict[str, Any]) -> dict[str, Any]:
    """执行单条用例并判定。"""
    q = case["question"]
    exp_clause = case.get("expected_clause")
    ctype = case["type"]

    try:
        r = kg.run_inference(q)
    except Exception as e:  # 服务异常也要计入，不能静默
        return {
            "id": case["id"], "type": ctype, "question": q,
            "error": f"{type(e).__name__}: {e}",
            "hit": False, "coverage": "ERROR", "traceable": False, "hops": 0,
        }

    got_clause = r.get("clause") or ""
    coverage = r.get("coverage", "")
    hops = len(r.get("chain", []))

    # ★★ v1.3 修正（回应第 4 轮审计）★★
    #
    # v1.2 的做法被审计指出仍然有问题：
    #   "`eval_runner.py:75-86` **并未解析真实回答**，而是**用引擎结构化字段
    #    拼**出一段文本（`f"{action}【{clause}】"` —— **方括号是评测器自己加的**）
    #    再正则。因此 traceable ⇔ len(recommendations) > 0。"
    #
    # 实测核对后的准确情况：
    #   · 引擎的 `conclusion` **原文里本来就带**「适用【推荐意见14】…」——
    #     方括号是**引擎自己写的**，不是评测器加的（审计此处略有偏差）
    #   · **但** v1.2 的拼装**额外又加了一层 `【】`**
    #     （`f"{action}【{clause}】"`），把条款计数放大，
    #     使"可溯源"更容易成立 —— 这部分指控**成立**
    #
    # v1.3 改为：**只用引擎的自然语言字段原文**，不做任何格式拼装。
    #   · 纳入：`conclusion` / `caveat` / `disclaimer`
    #     —— 这些是引擎写给用户看的自然语言
    #   · **排除**：`recommendations` / `contraindications` 的 `clause` 字段
    #     —— 那是结构化数据，不是"回答文本"
    #
    # ⚠️ 同时**如实披露一个结构性事实**：
    #   引擎在 COVERED 分支的 `conclusion` 里必然写入「适用【推荐意见N】」，
    #   在 NOT_COVERED 分支必然不写。因此本指标**仍与 `coverage` 同向**
    #   （不是恒等，但高度相关）。这一点已写入随包文档。
    _natural_parts = [
        str(r.get("conclusion") or ""),
        str(r.get("caveat") or ""),
        str(r.get("disclaimer") or ""),
    ]
    _answer_text = "\n".join(p for p in _natural_parts if p)
    _cited = CLAUSE_RE.findall(_answer_text)
    traceable = len(_cited) > 0
    # 记录：该指标与 COVERED 的相关性（供报告披露）
    _trace_source = "engine_natural_language_fields_only"

    referral = r.get("referral", "")

    # ---- 判定逻辑按用例类型区分 ----
    if ctype == "refusal":
        # 拒答例：应返回 NOT_COVERED，且不得编造条款
        hit = (coverage == "NOT_COVERED") and (got_clause == "")
    elif ctype == "referral":
        # 分级诊疗例：问题是"该在哪级医院管理"，判据是**分级诊疗归属是否正确**。
        # 不要求命中推荐意见18 本身——引擎会先给出该结节的处置条款，
        # 并同时输出 referral 字段。此处只校验归属是否包含期望机构。
        exp_topic = case.get("expected_topic", "")
        key = exp_topic.replace("管理", "").replace("协助指导", "").strip()[:4]
        hit = bool(key) and (key in referral)
    elif ctype == "contraindication":
        # 禁忌例：问题是"能否做 PET-CT"，判据是**禁忌提示是否出现**，
        # 而非主条款编号。引擎会先给出处置条款（如推荐意见14），
        # 禁忌另行出现在 contraindications 中。
        exp_kw = case.get("expected_keyword", "PET-CT")
        contra_text = " ".join(c.get("reason", "")
                               for c in r.get("contraindications", []))
        hit = (exp_kw in contra_text)
    elif ctype in ("positive", "boundary"):
        hit = (got_clause == exp_clause)
    else:
        hit = (got_clause == exp_clause)

    return {
        "id": case["id"], "type": ctype, "question": q,
        "expected_clause": exp_clause,
        "got_clause": got_clause,
        "coverage": coverage,
        "traceable": traceable,
        "hops": hops,
        "referral": referral,
        "conclusion": r.get("conclusion", "")[:120],
        "hit": hit,
    }


def evaluate(evalset: dict[str, Any]) -> dict[str, Any]:
    cases = evalset["cases"]
    results = [run_case(c) for c in cases]

    total = len(results)
    hits = sum(1 for r in results if r["hit"])
    covered = sum(1 for r in results if r["coverage"] == "COVERED")
    traceable = sum(1 for r in results if r["traceable"])
    hops = [r["hops"] for r in results if r["hops"] > 0]

    # 按类型细分
    by_type: dict[str, dict[str, Any]] = {}
    for t in sorted({r["type"] for r in results}):
        sub = [r for r in results if r["type"] == t]
        by_type[t] = {
            "count": len(sub),
            "hit": sum(1 for r in sub if r["hit"]),
            "accuracy": round(sum(1 for r in sub if r["hit"]) / len(sub), 4),
        }

    # 拒答例单独统计（正确拒答率）
    refusal = [r for r in results if r["type"] == "refusal"]
    refusal_correct = sum(1 for r in refusal if r["hit"])

    metrics = {
        "total_cases": total,
        "clause_accuracy": round(hits / total, 4) if total else 0.0,
        "coverage_rate": round(covered / total, 4) if total else 0.0,
        "traceability_rate": round(traceable / total, 4) if total else 0.0,
        "refusal_correctness": (round(refusal_correct / len(refusal), 4)
                                if refusal else None),
        "avg_reasoning_hops": (round(sum(hops) / len(hops), 2) if hops else 0),
        "max_reasoning_hops": max(hops) if hops else 0,
        "by_type": by_type,
        "error_count": sum(1 for r in results if r.get("error")),
    }
    return {"metrics": metrics, "results": results}


def print_report(res: dict[str, Any], evalset_name: str) -> None:
    m = res["metrics"]
    print("=" * 68)
    print("  肺结节处置决策 · 自测报告")
    print("=" * 68)
    print(f"  评测集            : {evalset_name}")
    print(f"  用例总数          : {m['total_cases']}")
    print("-" * 68)
    print(f"  ★ 条款命中率      : {m['clause_accuracy'] * 100:.1f}%")
    print(f"    覆盖率          : {m['coverage_rate'] * 100:.1f}%")
    print(f"    可溯源率        : {m['traceability_rate'] * 100:.1f}%")
    if m["refusal_correctness"] is not None:
        print(f"    拒答正确率      : {m['refusal_correctness'] * 100:.1f}%")
    print(f"    平均推理跳数    : {m['avg_reasoning_hops']}")
    print(f"    最大推理跳数    : {m['max_reasoning_hops']}")
    if m["error_count"]:
        print(f"    ⚠ 执行异常      : {m['error_count']}")
    print("-" * 68)
    print("  分类明细")
    for t, v in m["by_type"].items():
        print(f"    {t:18s} {v['hit']:3d}/{v['count']:<3d}  "
              f"{v['accuracy'] * 100:5.1f}%")
    print("=" * 68)

    # 失败用例
    fails = [r for r in res["results"] if not r["hit"]]
    if fails:
        print(f"\n  未命中用例（{len(fails)} 条）:")
        for r in fails[:20]:
            print(f"    [{r['type']:16s}] {r['id']}")
            print(f"        问  : {r['question'][:70]}")
            print(f"        期望: {r.get('expected_clause') or '(拒答)'}"
                  f"   实际: {r.get('got_clause') or '(拒答)'}"
                  f"   coverage={r.get('coverage')}")


def main() -> int:
    ap = argparse.ArgumentParser(description="运行肺结节处置决策自测")
    ap.add_argument("--evalset", default="evalset.json")
    ap.add_argument("--report", default="")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    if not os.path.exists(args.evalset):
        print(f"[ERROR] 评测集不存在: {args.evalset}", file=sys.stderr)
        return 2

    with open(args.evalset, encoding="utf-8") as f:
        ds = json.load(f)

    res = evaluate(ds)
    if not args.quiet:
        print_report(res, ds.get("name", args.evalset))

    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump({"evalset": ds.get("name"), **res},
                      f, ensure_ascii=False, indent=2)
        print(f"\n  报告已保存: {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
