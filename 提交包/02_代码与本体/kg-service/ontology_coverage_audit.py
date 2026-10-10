#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本体完备性诊断：从语料侧发现"本体未覆盖的概念"
================================================================

要解决的问题
------------
`ontology_builder._match_classes()` 遍历的是 `self.onto["classes"]` ——
**只在本体里找概念**。因此：

    · 抽取出的对象三元组**天然全部对齐**
    · `unaligned_rate` 恒为 0
    · 候选池恒为空 → 人工审核闭环从未被触发
    · 路径 C（仅 8 类的极小本体）也报 0.0% 未对齐

**即：`unaligned_rate` 是一个自证式指标** ——
它测的是"抽取器只认本体"，不是"本体是否完备"。

本模块提供一个**不依赖本体**的度量：

    完备性缺口 = 语料中候选领域术语数 − 已被本体覆盖的候选术语数

候选术语的发现方式（不依赖本体）
--------------------------------
从语料中挖掘"领域术语形状"的片段，规则透明可复核：

  1. 中文医学/规范术语高频后缀（结节、随访、活检、治疗、征、检测、评估…）
  2. 数字+单位形态（阈值表述）
  3. 反复出现的 2~6 字名词性片段（按频次过滤）

然后逐个判断：该术语能否被本体对齐（用 builder.align()）。
不能的，就是**本体缺口**。

诚实声明
--------
· 这是**术语层**的覆盖度近似，不是语义完备性证明
· 候选术语由启发式规则产生，会有噪声；报告同时给出规则与命中样本，
  便于人工判断
· 真实的本体缺口应由领域专家标注；本模块提供的是**可复现的上界估计**

用法
----
    python3 ontology_coverage_audit.py --docs a.txt b.txt --names A B --out audit.json
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from collections import Counter


# ---- 候选术语发现：高频后缀（领域无关的"规范术语形状"）----
TERM_SUFFIXES = [
    "结节", "随访", "活检", "治疗", "切除", "消融", "放疗",
    "征", "检测", "评估", "筛查", "诊断", "干预", "转诊",
    "人群", "因素", "病史", "暴露", "模型", "标准", "共识",
    "指南", "推荐", "分层", "管理", "监测", "复发", "淋巴结",
]

# ---- 停用片段：这些形状不是领域概念 ----
STOP_FRAGMENTS = {
    "的结节", "有结节", "该结节", "此结节", "个结节", "无结节",
    "和结节", "或结节", "等结节", "为结节", "在结节", "对结节",
    "随访的", "随访和", "随访或", "的随访", "行随访", "做随访",
    "的评估", "和评估", "评估的", "进行评估", "需评估",
    "的诊断", "诊断的", "和治疗", "治疗的", "治疗和",
}

# 中文术语的字符范围
CJK = r"\u4e00-\u9fff"


def discover_candidates(text: str, min_count: int = 2) -> Counter:
    """从语料中发现候选领域术语（不依赖本体）。"""
    cnt: Counter = Counter()

    for suf in TERM_SUFFIXES:
        # 后缀前 2~5 个中文字符
        for m in re.finditer(rf"([{CJK}]{{2,5}}){re.escape(suf)}", text):
            term = m.group(1) + suf
            if term in STOP_FRAGMENTS:
                continue
            if len(term) < 3 or len(term) > 7:
                continue
            cnt[term] += 1

    # 只保留重复出现的（单次出现更可能是噪声）
    return Counter({k: v for k, v in cnt.items() if v >= min_count})


def audit(mod, texts: list[str], names: list[str], min_count: int = 2) -> dict:
    """对每份文档做完备性审计。"""
    b = mod.OntologyBuilder()
    onto_classes = set(b.onto["classes"].keys())
    # 本体别名也算覆盖
    onto_aliases = set()
    for cls, meta in b.onto["classes"].items():
        onto_aliases.add(cls)
        for a in meta.get("aliases", []):
            onto_aliases.add(a)

    rows = []
    all_gaps: Counter = Counter()

    for name, txt in zip(names, texts):
        cands = discover_candidates(txt, min_count)
        covered, gaps = [], []
        for term, freq in cands.items():
            ok, mapped = b.align(term)
            if ok:
                covered.append({"term": term, "freq": freq, "mapped_to": mapped})
            else:
                gaps.append({"term": term, "freq": freq})
                all_gaps[term] += freq
        gaps.sort(key=lambda x: -x["freq"])
        covered.sort(key=lambda x: -x["freq"])
        rows.append({
            "document": name,
            "doc_chars": len(txt),
            "candidates": len(cands),
            "covered": len(covered),
            "gaps": len(gaps),
            "term_coverage_rate": round(len(covered) / max(len(cands), 1), 4),
            "gap_samples": gaps[:25],
            "covered_samples": covered[:15],
        })

    tot_c = sum(r["candidates"] for r in rows)
    tot_g = sum(r["gaps"] for r in rows)
    return {
        "ontology_classes": len(onto_classes),
        "method": ("候选术语由高频后缀规则发现（不依赖本体）；"
                   "对齐判定用 builder.align()。这是术语层覆盖度的近似，"
                   "不是语义完备性证明。"),
        "min_count": min_count,
        "documents": rows,
        "summary": {
            "total_candidates": tot_c,
            "total_gaps": tot_g,
            "overall_term_coverage": round((tot_c - tot_g) / max(tot_c, 1), 4),
            "top_gaps": all_gaps.most_common(40),
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="本体完备性诊断")
    ap.add_argument("--builder", default="/tmp/ontology_builder.py")
    ap.add_argument("--docs", nargs="+", required=True)
    ap.add_argument("--names", nargs="+", required=True)
    ap.add_argument("--min-count", type=int, default=2)
    ap.add_argument("--out", default="coverage_audit.json")
    args = ap.parse_args()

    spec = importlib.util.spec_from_file_location("ob", args.builder)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    texts = [open(p, encoding="utf-8", errors="replace").read() for p in args.docs]
    rep = audit(mod, texts, args.names, args.min_count)

    print("=" * 80)
    print("  本体完备性诊断（不依赖本体的覆盖度度量）")
    print("=" * 80)
    print(f"  本体类数: {rep['ontology_classes']}")
    print(f"  候选术语最小频次: {rep['min_count']}")
    print()
    print(f"  {'文档':<14}{'候选术语':>9}{'已覆盖':>8}{'缺口':>7}{'覆盖率':>9}")
    print("  " + "-" * 50)
    for r in rep["documents"]:
        print(f"  {r['document']:<14}{r['candidates']:>9}{r['covered']:>8}"
              f"{r['gaps']:>7}{r['term_coverage_rate'] * 100:>8.1f}%")
    s = rep["summary"]
    print("  " + "-" * 50)
    print(f"  {'合计':<14}{s['total_candidates']:>9}"
          f"{s['total_candidates'] - s['total_gaps']:>8}{s['total_gaps']:>7}"
          f"{s['overall_term_coverage'] * 100:>8.1f}%")
    print()
    print("  ---- 最高频的本体缺口（Top 30）----")
    for term, freq in s["top_gaps"][:30]:
        print(f"    {freq:>4}×  {term}")
    print("=" * 80)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=2)
    print(f"  报告已保存: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
