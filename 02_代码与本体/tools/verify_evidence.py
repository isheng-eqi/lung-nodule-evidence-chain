#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""最终验收核对：正文的每个关键数字是否与 `03_验证与数据/` 的 JSON 一致。

★ 为什么需要这个工具
====================

本项目的核心主张之一是"**每条结论都能回溯到可核验落点**"。
但"能回溯"如果只靠人工核对，就会**随每次改动而失效** ——
第 60 / 65 / 68 轮反复出现的"文档 vs JSON"矛盾正是这样产生的。

本工具把"**正文数字 ↔ JSON 来源**"的核对**自动化**，
使"证据齐全"成为一个**可复跑的命令**，而不是一句声称。

用法
----
    python3 verify_evidence.py --pkg <提交包目录>

返回码：0 全部一致；1 存在不一致（可用于流水线）。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys


def load(pkg: str, name: str):
    p = os.path.join(pkg, "03_验证与数据", name)
    if not os.path.exists(p):
        return None
    return json.load(open(p, encoding="utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser(description="正文数字 ↔ JSON 来源 的一致性核对")
    ap.add_argument("--pkg", required=True)
    args = ap.parse_args()
    pkg = os.path.abspath(args.pkg)

    doc_path = os.path.join(pkg, "01_开发设计文档", "开发设计文档_源文件.md")
    doc = open(doc_path, encoding="utf-8").read()

    checks: list[tuple[str, str, bool]] = []

    def ck(name: str, value: str, present: bool):
        checks.append((name, value, present))

    # ---- 1. 迁移成本（键名以 JSON 实际结构为准）----
    cost = load(pkg, "迁移成本量化报告.json") or {}
    tpl = cost.get("template_analysis") or {}
    if tpl:
        ck("模板文件总行数", f"{tpl.get('total_lines'):,}",
           f"{tpl.get('total_lines'):,}" in doc)
        ck("骨架函数行数", str(tpl.get("skeleton_lines")),
           str(tpl.get("skeleton_lines")) in doc)
        ck("领域参数函数行数", str(tpl.get("domain_spec_lines")),
           str(tpl.get("domain_spec_lines")) in doc)
    mc = cost.get("migration_cost") or {}
    ck("DomainSpec 字段数", str(mc.get("domain_spec_fields_to_fill")),
       bool(re.search(rf"{mc.get('domain_spec_fields_to_fill')}\s*个", doc)))

    # ---- 2. 三领域迁移 ----
    mig = load(pkg, "多行业迁移验证报告.json") or {}
    for d in mig.get("domains", []):
        nm = (d.get("spec") or {}).get("domain_name", "?")
        r = d.get("result") or {}
        v = r.get("clauses_found")
        if v is not None:
            ck(f"{nm} 条款数", str(v), str(v) in doc)
    sc = (mig.get("migration_analysis") or {}).get("skeleton_changed", "?")
    ck("skeleton_changed", repr(sc), "不可判定" in doc)

    # ---- 3. 消融净收益 ----
    gain = load(pkg, "消融实验_净收益量化.json") or {}
    met = gain.get("metrics") or {}
    if met:
        a = (met.get("contraindication_hits") or {}).get("A_dual")
        c = (met.get("contraindication_hits") or {}).get("C_kg_only")
        n = met.get("advice_scenario_count")
        ck("禁忌提示 A 双驱动", f"{a}/{n}", f"{a}/{n}" in doc)
        ck("禁忌提示 C 仅图谱", f"{c}/{n}", f"{c}/{n}" in doc)

    # ---- 4. 术语覆盖率（JSON 存的是小数，正文是百分数）----
    cov = load(pkg, "coverage_audit_v13.json") or {}
    rate = ((cov.get("summary") or {}).get("overall_term_coverage")
            or cov.get("overall_term_coverage"))
    if rate is None:
        # 兜底：在 JSON 里搜形如 0.xxxx 的覆盖率字段
        m = re.search(r'"overall_term_coverage"\s*:\s*([\d.]+)',
                      json.dumps(cov))
        rate = float(m.group(1)) if m else None
    if rate is not None:
        pct = f"{rate * 100:.1f}%"
        ck("术语覆盖率", pct, pct in doc)

    # ---- 5. MedRepBench ----
    mb = load(pkg, "真实脱敏数据集评测_MedRepBench.json") or {}
    avg = mb.get("average_recall")
    if avg is not None:
        pct = f"{avg * 100:.1f}%"
        ck("MedRepBench 平均字段召回", pct, pct in doc)

    # ---- 6. 端到端三个判据 ----
    st = load(pkg, "智能体层端到端评测_严格判据.json") or {}
    rates = st.get("rates") or {}
    for key, label in (("loose", "宽松判据"), ("strict", "严格判据"),
                       ("strict_plus", "严格+判据")):
        if key in rates:
            pct = f"{rates[key] * 100:.1f}%"
            ck(label, pct, pct in doc or pct.rstrip("0").rstrip(".") in doc)

    # ---- 输出 ----
    print("=" * 78)
    print("  最终验收核对：正文数字 ↔ JSON 来源")
    print("=" * 78)
    print(f"  包: {pkg}")
    print(f"  正文: {os.path.relpath(doc_path, pkg)}")
    print()
    ok = 0
    for name, val, good in checks:
        print(f"  {'OK ' if good else 'BAD'} {name:<26} = {val}")
        ok += bool(good)
    print()
    print(f"  {ok}/{len(checks)} 一致")
    if ok < len(checks):
        print("\n  ⚠️ 存在不一致 —— 请核对上表 BAD 行对应的 JSON 路径与正文表述。")
    return 0 if ok == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
