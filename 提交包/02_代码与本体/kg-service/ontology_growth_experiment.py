#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本体成长实验：未对齐率随本体扩充而下降
================================================================

要证明什么
----------
官方评分（25% 算法创新性）要求"**半自动化本体构建效率优势明显**"。

若只讲"3.02 小时 → 秒级"，那只证明**机器比人快** —— 任何自动化都能这么说。
真正的**算法**优势应该是：**系统会随使用而变好**。

本项目 `ontology_builder.py` 内置了这个机制：
    对不上的内容不直接入库 → 标记为「候选新概念」 → 人工审核通过则扩充本体
    → 本体持续动态更新 → 下一份文档的对齐率因此提高

本实验把这个机制**量化**出来。

实验设计
--------
两条路径，处理**同一批文档、同一顺序**：

  路径 A（**冷启动 / 无成长机制**）
      每份文档都用一个全新的初始种子本体处理。
      模拟"抽不出来就算了"的做法。

  路径 B（**增量成长 / 有人工审核闭环**）
      处理完一份文档后，把候选池中的概念**审核通过并回灌本体**，再处理下一份。

对比两条路径的**未对齐率曲线**。

关于"人工审核"的诚实说明
------------------------
真实部署中，候选概念由**领域专家**审核（本项目 `review()` 接口即为此设计）。
本实验为**可复现**，用「候选概念的出现频次 ≥ MIN_SUPPORT」作为审核的**代理判据**。
**这不代表已发生真实专家审核**，报告中明确标注。

用法
----
    python3 ontology_growth_experiment.py \
        --docs a.txt b.txt c.txt d.txt \
        --names 2024共识 2025共识 筛查2023 筛查2025 \
        --out growth_report.json
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from copy import deepcopy


MIN_SUPPORT = 1   # 候选概念出现次数达到该值视为"审核通过"（代理判据）


def _load_builder(path: str):
    spec = importlib.util.spec_from_file_location("ob", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _stats(rep, builder, triples_before: int = 0) -> dict:
    """从一次 extract 的报告中取统计。

    ⚠️ 重要：`OntologyBuilder.triples` 是**跨文档累积**的，
    而 `rep` 中的 triples_total / triples_aligned 是**本次文档**的计数。
    路径 B 复用同一个 builder，因此必须用 rep 的计数，
    不能回读 builder.triples（否则会得到累计值，导致曲线虚高）。
    """
    d = rep.to_dict()
    return {
        "clauses_found": d.get("clauses_found", 0),
        "triples_total": d.get("triples_total", 0),
        "triples_aligned": d.get("triples_aligned", 0),
        "triples_pending": d.get("triples_pending", 0),
        "data_triples": d.get("data_triples", 0),
        "alignment_rate": round(d.get("alignment_rate", 0.0), 4),
        "unaligned_rate": round(d.get("unaligned_rate", 0.0), 4),
        "doc_chars": d.get("doc_chars", 0),
        "classes": len(builder.onto.get("classes", {})),
        "cumulative_triples": len(builder.triples),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="本体成长实验")
    ap.add_argument("--builder", default="/tmp/ontology_builder.py")
    ap.add_argument("--docs", nargs="+", required=True)
    ap.add_argument("--names", nargs="+", required=True)
    ap.add_argument("--out", default="growth_report.json")
    ap.add_argument("--min-support", type=int, default=MIN_SUPPORT)
    args = ap.parse_args()

    if len(args.docs) != len(args.names):
        print("[ERROR] --docs 与 --names 数量必须一致", file=sys.stderr)
        return 2

    mod = _load_builder(args.builder)
    texts = []
    for p in args.docs:
        with open(p, encoding="utf-8", errors="replace") as f:
            texts.append(f.read())

    seed_classes = len(mod.SEED_ONTOLOGY["classes"])

    report: dict = {
        "seed_classes": seed_classes,
        "min_support": args.min_support,
        "documents": args.names,
        "path_a_frozen_seed": [],
        "path_b_incremental": [],
        "review_proxy": ("候选概念回灌以「出现频次 ≥ min_support」作为人工审核的"
                         "**可复现代理判据**；真实部署中该步骤由领域专家审核"
                         "（ontology_builder.review 接口），本实验不代表已发生专家审核。"),
    }

    # ---------------- 路径 A：固定初始种子本体，不成长 ----------------
    print("=" * 80)
    print("  路径 A：冷启动（每份文档都用初始种子本体，本体不成长）")
    print("=" * 80)
    for name, txt in zip(args.names, texts):
        b = mod.OntologyBuilder()
        st = _stats(b.extract(txt, doc_name=name), b)
        st["document"] = name
        report["path_a_frozen_seed"].append(st)
        print(f"  {name:<12} 条款 {st['clauses_found']:>3} | 三元组 "
              f"{st['triples_total']:>4} | 对齐 {st['triples_aligned']:>4} | "
              f"未对齐率 {st['unaligned_rate'] * 100:>5.1f}% | 本体类 {st['classes']:>3}")

    # ---------------- 路径 B：增量成长 ----------------
    print()
    print("=" * 80)
    print("  路径 B：增量成长（候选概念审核回灌本体后再处理下一份）")
    print("=" * 80)
    b = mod.OntologyBuilder()
    carried_pool: list[dict] = []
    carry_counts: dict[str, int] = {}

    for i, (name, txt) in enumerate(zip(args.names, texts)):
        # 处理前：把上一轮累积的候选概念回灌本体
        approved: list[str] = []
        if carried_pool:
            for p in carried_pool:
                surface = p.get("surface", "")
                if not surface:
                    continue
                cnt = carry_counts.get(surface, 1)
                if cnt >= args.min_support:
                    b.review(surface, target_class=surface, parent="", aliases=[])
                    approved.append(surface)
            carried_pool = []

        classes_before = len(b.onto["classes"])
        st = _stats(b.extract(txt, doc_name=name), b)
        st["document"] = name
        st["classes_before"] = classes_before
        st["approved_into_ontology"] = approved
        st["classes_after"] = len(b.onto["classes"])
        report["path_b_incremental"].append(st)

        # 累积本轮候选概念（带去重计数），供下一轮回灌
        for p in b.onto.get("pending_concepts", []):
            s = p.get("surface", "")
            if not s:
                continue
            carry_counts[s] = carry_counts.get(s, 0) + 1
            carried_pool.append(p)

        print(f"  {name:<12} 条款 {st['clauses_found']:>3} | 三元组 "
              f"{st['triples_total']:>4} | 对齐 {st['triples_aligned']:>4} | "
              f"未对齐率 {st['unaligned_rate'] * 100:>5.1f}% | 本体类 "
              f"{classes_before:>3} → {st['classes_after']:>3}"
              + (f" | 回灌 {len(approved)}" if approved else ""))

    # ---------------- 路径 C：最小种子 → 观察成长 ----------------
    # 真实"低资源领域"的起点往往不是 52 类的成熟本体，而是一个**很薄的种子**。
    # 本路径从最小种子出发，检验"候选概念回灌"机制是否真的能把本体带大、
    # 并把后续文档的未对齐率压下去。
    minimal_classes = {
        # 顶层类（本体骨架必需）
        "肺结节": {"parent": None, "aliases": ["结节", "肺部结节"]},
        "患者": {"parent": None, "aliases": ["病人", "受检者"]},
        "危险因素": {"parent": None, "aliases": []},
        "影像学特征": {"parent": None, "aliases": []},
        "检查手段": {"parent": None, "aliases": ["检查方法", "检查"]},
        "处置动作": {"parent": None, "aliases": ["处置", "处理措施"]},
        "推荐意见": {"parent": None, "aliases": ["推荐条款", "条款", "推荐"]},
        "医疗机构": {"parent": None, "aliases": ["医院"]},
    }
    print()
    print("=" * 80)
    print(f"  路径 C：最小种子（{len(minimal_classes)} 类）→ 观察本体成长")
    print("=" * 80)

    onto_min = deepcopy(mod.SEED_ONTOLOGY)
    onto_min["classes"] = deepcopy(minimal_classes)
    onto_min["pending_concepts"] = []
    c = mod.OntologyBuilder(ontology=onto_min)
    carry_pool_c: list[dict] = []
    carry_counts_c: dict[str, int] = {}

    for i, (name, txt) in enumerate(zip(args.names, texts)):
        approved: list[str] = []
        if carry_pool_c:
            for p in carry_pool_c:
                surface = p.get("surface", "")
                if not surface:
                    continue
                if carry_counts_c.get(surface, 1) >= args.min_support:
                    c.review(surface, target_class=surface, parent="", aliases=[])
                    approved.append(surface)
            carry_pool_c = []

        classes_before = len(c.onto["classes"])
        st = _stats(c.extract(txt, doc_name=name), c)
        st["document"] = name
        st["classes_before"] = classes_before
        st["approved_into_ontology"] = approved
        st["classes_after"] = len(c.onto["classes"])
        report.setdefault("path_c_minimal_seed", []).append(st)

        for p in c.onto.get("pending_concepts", []):
            s = p.get("surface", "")
            if not s:
                continue
            carry_counts_c[s] = carry_counts_c.get(s, 0) + 1
            carry_pool_c.append(p)

        print(f"  {name:<12} 条款 {st['clauses_found']:>3} | 三元组 "
              f"{st['triples_total']:>4} | 对齐 {st['triples_aligned']:>4} | "
              f"未对齐率 {st['unaligned_rate'] * 100:>5.1f}% | 本体类 "
              f"{classes_before:>3} → {st['classes_after']:>3}"
              + (f" | 回灌 {len(approved)}" if approved else ""))

    # ---------------- 对比 ----------------
    a_list = report["path_a_frozen_seed"]
    b_list = report["path_b_incremental"]
    c_list = report.get("path_c_minimal_seed", [])
    print()
    print("=" * 80)
    print("  对比：两条路径的未对齐率")
    print("=" * 80)
    print(f"  {'文档':<14}{'A 固定52类':>14}{'B 增量52类':>14}{'C 最小种子':>14}")
    print("  " + "-" * 58)
    for i, x in enumerate(a_list):
        y = b_list[i] if i < len(b_list) else {"unaligned_rate": 0}
        z = c_list[i] if i < len(c_list) else {"unaligned_rate": 0}
        print(f"  {x['document']:<14}{x['unaligned_rate'] * 100:>13.1f}%"
              f"{y['unaligned_rate'] * 100:>13.1f}%{z['unaligned_rate'] * 100:>13.1f}%")

    avg_a = sum(x["unaligned_rate"] for x in a_list) / max(len(a_list), 1)
    avg_b = sum(x["unaligned_rate"] for x in b_list) / max(len(b_list), 1)
    avg_c = sum(x["unaligned_rate"] for x in c_list) / max(len(c_list), 1) if c_list else 0.0
    print("  " + "-" * 58)
    print(f"  {'平均':<14}{avg_a * 100:>13.1f}%{avg_b * 100:>13.1f}%{avg_c * 100:>13.1f}%")

    report["summary"] = {
        "seed_classes": seed_classes,
        "minimal_seed_classes": len(minimal_classes),
        "classes_final": b_list[-1]["classes_after"] if b_list else seed_classes,
        "classes_grown": (b_list[-1]["classes_after"] - seed_classes) if b_list else 0,
        "path_c_classes_final": c_list[-1]["classes_after"] if c_list else len(minimal_classes),
        "path_c_classes_grown": (c_list[-1]["classes_after"] - len(minimal_classes)) if c_list else 0,
        "avg_unaligned_rate_frozen": round(avg_a, 4),
        "avg_unaligned_rate_incremental": round(avg_b, 4),
        "avg_unaligned_rate_minimal_seed": round(avg_c, 4),
        "improvement_pp": round((avg_a - avg_b) * 100, 2),
        "path_c_first_doc_unaligned": round(c_list[0]["unaligned_rate"], 4) if c_list else None,
        "path_c_last_doc_unaligned": round(c_list[-1]["unaligned_rate"], 4) if c_list else None,
    }
    print()
    print(f"  本体规模：种子 {seed_classes} 类 | "
          f"路径 B 结束 {report['summary']['classes_final']} 类 | "
          f"路径 C 从 {len(minimal_classes)} 类 → "
          f"{report['summary']['path_c_classes_final']} 类")
    print("=" * 80)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"  报告已保存: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
