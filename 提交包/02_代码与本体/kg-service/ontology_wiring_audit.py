#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本体接线审计：找出"定义了但抽取不到"的类目
================================================================

要解决的问题
------------
在金融领域迁移验证中发现：本体定义了 15 个类目，
但语料只命中了 9 个（60%）。诊断后发现**三种不同原因**：

| 原因 | 例 | 判断依据 |
|---|---|---|
| **类目未接到抽取关系上** | 担保（原文 15 次） | 类目不在任何 `relations` 的 dom/rng 分支下 |
| **受约束抽取漏检** | ｜在分支下但文本未命中 |
| **本体设计冗余** | 信息披露 / 抵押 / 资金监控 | 原文中**该概念完全不存在** |

**第 1 种是最隐蔽的**：本体里明明定义了，但因为没接到关系上，
抽取器**根本不会去搜索它** —— 表现为"覆盖率莫名偏低"，而代码不报错。

**这个缺陷在医疗领域同样存在**：`吸烟史`（危险因素分支下的类目）
因 `危险因素` 分支未挂到任何关系上而从未被抽取。

本模块把这次人工诊断**固化为可复用工具**，
使每次领域迁移都能自动发现这类"接线遗漏"。

用法
----
    python3 ontology_wiring_audit.py \
        --template kg-service/workflow_template.py \
        --spec medical \
        --corpus corpus/肺结节诊治中国专家共识2024年版_全文.txt \
        --out wiring_audit.json
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from datetime import datetime, timezone


def load_template(path: str):
    spec = importlib.util.spec_from_file_location("wt", path)
    m = importlib.util.module_from_spec(spec)
    sys.modules["wt"] = m
    spec.loader.exec_module(m)
    return m


def audit(spec_obj, corpus_text: str) -> dict:
    """对一个 DomainSpec 做接线审计。"""
    classes = spec_obj.classes
    relations = spec_obj.relations

    # ---- 1. 计算被 relations 的 dom/rng 覆盖的分支 ----
    rel_branches = set()
    rel_detail: list[dict] = []
    for r, (dom, rng, zh) in relations.items():
        rel_branches.add(dom)
        rel_branches.add(rng)
        rel_detail.append({"relation": r, "dom": dom, "rng": rng, "zh": zh})

    def in_branch(cls: str) -> bool:
        cur = cls
        while cur:
            if cur in rel_branches:
                return True
            cur = classes.get(cur, {}).get("parent")
        return False

    roots = {c for c, meta in classes.items() if not meta.get("parent")}
    vocab = set(classes) - roots

    # ---- 2. 逐类目分类 ----
    wired_and_present: list[dict] = []      # 接线正确 + 语料有 → 应被抽取
    wired_but_absent: list[dict] = []       # 接线正确 + 语料无 → 该文档未涉及
    unwired_but_present: list[dict] = []    # ★ 未接线 + 语料有 → **漏检根因**
    unwired_and_absent: list[dict] = []     # 未接线 + 语料无 → 双重问题
    vocab_absent: list[str] = []            # 本体冗余候选（原文完全没有）

    for cls in sorted(vocab):
        meta = classes[cls]
        names = [cls] + list(meta.get("aliases", []))
        hit_names = [n for n in names if n and n in corpus_text]
        present = bool(hit_names)
        wired = in_branch(cls)

        rec = {"class": cls, "parent": meta.get("parent"),
               "in_relation_branch": wired,
               "matched_names": hit_names,
               "matched_by": ("exact" if cls in hit_names else
                              (f"alias:{hit_names[0]}" if hit_names else ""))}
        if wired and present:
            wired_and_present.append(rec)
        elif wired and not present:
            wired_but_absent.append(rec)
            vocab_absent.append(cls)
        elif not wired and present:
            unwired_but_present.append(rec)
        else:
            unwired_and_absent.append(rec)
            vocab_absent.append(cls)

    total = len(vocab)
    effectively_wired = len(wired_and_present) + len(wired_but_absent)
    return {
        "domain_id": getattr(spec_obj, "domain_id", ""),
        "domain_name": getattr(spec_obj, "domain_name", ""),
        "corpus_chars": len(corpus_text),
        "vocab_size": total,
        "relation_count": len(relations),
        "relations": rel_detail,
        "wiring_coverage": round(effectively_wired / max(total, 1), 4),
        "wired_and_present": wired_and_present,
        "wired_but_absent": wired_but_absent,
        "unwired_but_present": unwired_but_present,
        "unwired_and_absent": unwired_and_absent,
        "ontology_redundancy_candidates": vocab_absent,
        "findings": {
            "unwired_but_present_count": len(unwired_but_present),
            "ontology_redundancy_count": len(vocab_absent),
            "verdict": (
                f"{len(unwired_but_present)} 个类目**在语料中出现但未接到抽取关系上** "
                f"（这是覆盖率偏低的根因，代码不会报错）；"
                f"{len(vocab_absent)} 个类目**在本份语料中完全不存在** "
                f"（本体设计冗余候选）。"
            ),
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="本体接线审计")
    ap.add_argument("--template", required=True)
    ap.add_argument("--spec", required=True,
                    choices=["medical", "finance"],
                    help="要审计哪个领域的 DomainSpec")
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--out", default="wiring_audit.json")
    args = ap.parse_args()

    m = load_template(args.template)
    spec_obj = (m.build_medical_spec() if args.spec == "medical"
                else m.build_finance_spec())
    text = open(args.corpus, encoding="utf-8", errors="replace").read()

    rep = audit(spec_obj, text)
    rep["generated_at"] = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    rep["purpose"] = ("找出「本体定义了但抽取不到」的类目，"
                      "区分「未接线」与「本体冗余」两种原因")

    print("=" * 80)
    print(f"  本体接线审计 · {rep['domain_name']}")
    print("=" * 80)
    print(f"  语料            : {os.path.basename(args.corpus)}（{rep['corpus_chars']:,} 字符）")
    print(f"  可命中类目      : {rep['vocab_size']}（已排除根类）")
    print(f"  关系定义        : {rep['relation_count']} 条")
    print(f"  接线覆盖率      : {rep['wiring_coverage']*100:.1f}%  "
          f"（{rep['vocab_size'] - len(rep['unwired_but_present']) - len(rep['unwired_and_absent'])}"
          f"/{rep['vocab_size']} 个类目在关系分支下）")
    print()
    print(f"  ✅ 接线正确且语料有  : {len(rep['wired_and_present'])} 个")
    print(f"  ○ 接线正确但语料无  : {len(rep['wired_but_absent'])} 个")
    print(f"  🔴 **未接线但语料有** : {len(rep['unwired_but_present'])} 个  ← 漏检根因")
    for r in rep["unwired_but_present"]:
        print(f"        {r['class']}（父类={r['parent']}，语料命中 {r['matched_names'][:2]}）")
    print(f"  ○ 未接线且语料无    : {len(rep['unwired_and_absent'])} 个")
    print()
    print(f"  ⚠️ 本体冗余候选（本语料完全没有）: {rep['ontology_redundancy_candidates']}")
    print("=" * 80)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=2)
    print(f"  报告已保存: {args.out}")
    print()
    print("  说明：`未接线但语料有` 是本工具的核心产出 ——")
    print("        这类缺陷不会报错，只表现为'覆盖率偏低'，人工很难发现。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
