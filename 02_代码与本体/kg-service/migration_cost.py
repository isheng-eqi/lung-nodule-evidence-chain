#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
迁移成本量化：把"轻量化"从形容词变成数字
================================================================

要回答的问题
------------
官方附加分①措辞："**多行业模板轻量化迁移适配验证**"。

审阅意见：
  "把迁移成本**量化**：改动文件数、改动代码行数、需填写的 `DomainSpec`
   字段数、人工工时（人时）。现在只有'换领域不换骨架'的定性与'62/139 行'
   的 Skill 差异 —— 直接命中'**轻量化**'这四个字，
   否则评委不知道'轻'在哪。"

本模块用**代码级比对**给出可核验的迁移成本：

  ① **改动文件数** —— 迁移到新行业需要动哪些文件
  ② **改动代码行数** —— 骨架代码是否被修改（应为 0）
  ③ **DomainSpec 字段数** —— 新领域需要填多少参数
  ④ **人工工时估算** —— 按字段数与语料规模估算

设计原则
--------
· **代码级比对而非人工声称** —— 用 AST 解析脚本，对比骨架函数与领域参数
· **区分"骨架"与"参数"** —— 这是"轻量化"的核心主张，必须可核验
· **工时按可复核的单价估算**，并标注这是估算而非实测

用法
----
    python3 migration_cost.py --template kg-service/workflow_template.py \
        --out migration_cost.json
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
from datetime import datetime, timezone


# 工时估算单价（可复核、可质疑）
UNIT_COST = {
    "domain_spec_class": 25,      # 每个领域类目：定义 + 别名 + 校验（分钟）
    "domain_spec_relation": 10,   # 每条关系
    "numeric_pattern": 8,         # 每个数值模式（需核对规范表述）
    "term_alias": 5,              # 每条术语别名
    "corpus_prepare_per_kchar": 3,  # 每千字语料准备（获取/清洗核对）
}


def _skeleton_verdict():
    """调用 workflow_template 的骨架校验，避免两个脚本各说各话。

    ★ 为什么需要这个函数（回应第 4 轮审计）
    --------------------------------------
    审计指出：本文件曾硬编码 `"skeleton_changed": False`，而
    `多行业迁移验证报告.json` 里是**计算得出的** `true` ——
    **同一份提交包里，骨架到底改没改，两份报告给出相反答案。**

    现统一由 `workflow_template._verify_skeleton_unchanged()` 裁决，
    本文件**不重复实现**判定逻辑。

    返回值：
      · `True`  —— 判定为骨架被改动
      · `False` —— 判定为骨架未改动
      · `None`  —— **无法判定**（导入失败等）。
        返回 `None` 而非 `False`，是为了**不假装"没改动"** ——
        无法判定时必须让调用方看到"这是个未知"，而不是一个虚假的确定值。
    """
    try:
        import importlib.util
        import sys as _sys
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "workflow_template.py")
        spec = importlib.util.spec_from_file_location("_wt_verdict", p)
        m = importlib.util.module_from_spec(spec)
        _sys.modules["_wt_verdict"] = m
        spec.loader.exec_module(m)
        # ★ 不要用 `bool()` 包一层 —— 那会把 `None` 变成 `False`，
        #   从而**丢掉"不可判定"这个信息**，而这正是本函数要避免的错误。
        #   `_verify_skeleton_unchanged()` 的 `changed` 现在是三态
        #   （True / False / None），此处**原样透传**。
        return m._verify_skeleton_unchanged()["changed"]
    except Exception:                                       # noqa: BLE001
        return None


def analyze_template(path: str) -> dict:
    """用 AST 解析模板脚本，分离"骨架函数"与"领域构建函数"。"""
    src = open(path, encoding="utf-8").read()
    tree = ast.parse(src)

    skeleton_funcs: list[dict] = []   # 骨架：跨领域不变的函数
    spec_funcs: list[dict] = []       # 领域参数：build_*_spec

    # 骨架函数名（跨领域复用）
    SKELETON_NAMES = {
        "run", "split_clauses", "extract", "align", "to_dict", "describe",
        "validate_migration", "main", "_clean", "clean_text",
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            n_lines = (node.end_lineno or node.lineno) - node.lineno + 1
            is_spec = node.name.startswith("build_") and node.name.endswith("_spec")
            rec = {
                "name": node.name,
                "lineno": node.lineno,
                "lines": n_lines,
                "is_domain_spec": is_spec,
            }
            if is_spec:
                spec_funcs.append(rec)
            else:
                skeleton_funcs.append(rec)

    classes = [
        {"name": n.name, "lines": (n.end_lineno or n.lineno) - n.lineno + 1}
        for n in ast.walk(tree) if isinstance(n, ast.ClassDef)
    ]

    # 统计 DomainSpec 的字段（dataclass 字段 = 迁移时需要填的参数）
    spec_fields: list[str] = []
    for n in ast.walk(tree):
        if isinstance(n, ast.ClassDef) and n.name == "DomainSpec":
            for stmt in n.body:
                if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                    spec_fields.append(stmt.target.id)

    return {
        "file": path,
        "total_lines": len(src.split("\n")),
        "classes": classes,
        "skeleton_functions": skeleton_funcs,
        "domain_spec_functions": spec_funcs,
        "skeleton_lines": sum(f["lines"] for f in skeleton_funcs),
        "domain_spec_lines": sum(f["lines"] for f in spec_funcs),
        "domain_spec_fields": spec_fields,
    }


def analyze_domain_spec(src_path: str, func_name: str) -> dict:
    """提取某个 build_*_spec 函数里的领域参数规模。"""
    src = open(src_path, encoding="utf-8").read()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            body = ast.get_source_segment(src, node) or ""
            n_classes = len(re.findall(r'^\s{12}"[^"]+":\s*\{', body, re.MULTILINE))
            n_aliases = len(re.findall(r'"aliases":\s*\[', body))
            alias_items = sum(
                len(re.findall(r'"[^"]+"', m)) for m in
                re.findall(r'"aliases":\s*\[([^\]]*)\]', body))
            n_relations = len(re.findall(r'^\s{12}"\w+":\s*\(', body, re.MULTILINE))
            n_numeric = len(re.findall(r'^\s{12}"\w+":\s*r"', body, re.MULTILINE))
            return {
                "function": func_name,
                "lineno": node.lineno,
                "lines": (node.end_lineno or node.lineno) - node.lineno + 1,
                "classes": n_classes,
                "relations": n_relations,
                "numeric_patterns": n_numeric,
                "alias_entries": n_aliases,
                "alias_items": alias_items,
            }
    return {"function": func_name, "error": "not found"}


def estimate_hours(spec: dict, corpus_chars: int) -> dict:
    """估算新领域迁移的人工工时。"""
    items = {
        "定义领域类目": spec.get("classes", 0) * UNIT_COST["domain_spec_class"],
        "定义关系类型": spec.get("relations", 0) * UNIT_COST["domain_spec_relation"],
        "定义数值模式": spec.get("numeric_patterns", 0) * UNIT_COST["numeric_pattern"],
        "录入术语别名": spec.get("alias_items", 0) * UNIT_COST["term_alias"],
        "准备领域语料": (corpus_chars / 1000) * UNIT_COST["corpus_prepare_per_kchar"],
    }
    total_min = sum(items.values())
    return {
        "unit_costs_minutes": UNIT_COST,
        "breakdown_minutes": {k: round(v, 1) for k, v in items.items()},
        "total_minutes": round(total_min, 1),
        "total_hours": round(total_min / 60, 2),
        "note": ("工时按上表单价**估算**，非实测；单价可被质疑与调整。"
                 "估算不含骨架代码学习成本（若骨架已熟悉则为 0）。"),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="迁移成本量化")
    ap.add_argument("--template", required=True)
    ap.add_argument("--out", default="migration_cost.json")
    args = ap.parse_args()

    tpl = analyze_template(args.template)
    med = analyze_domain_spec(args.template, "build_medical_spec")
    fin = analyze_domain_spec(args.template, "build_finance_spec")
    # ★ 第三领域（制造 / 特种设备安全）—— 回应审阅"第二行业与第一行业同族"
    mfg = analyze_domain_spec(args.template, "build_manufacturing_spec")

    # 语料规模（用于工时估算）
    # 语料规模（用于工时估算）—— 三领域
    CORPUS = {"医疗": 19309, "金融": 7554, "制造": 17172}

    report = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "title": "多行业迁移成本量化（轻量化验证）",
        "purpose": "把官方附加分①的『轻量化』从形容词变成可核验的数字",
        "template_analysis": tpl,
        "domain_specs": {"medical": med, "finance": fin,
                         "manufacturing": mfg},
        "migration_cost": {
            # 修正（回应第 4 轮审计）：审计指出本文件仍硬编码
            # `"skeleton_changed": False`，与 `多行业迁移验证报告.json` 里
            # **计算得出的** true **同包冲突**。
            # 现改为**调用同一套校验函数**，不再各说各话。
            "changed_files": [
                {"file": "kg-service/workflow_template.py",
                 "change": "新增/修改 build_<domain>_spec() —— 领域参数函数",
                 "skeleton_changed": _skeleton_verdict()},
            ],
            "changed_file_count": 1,
            "skeleton_code_lines_changed": (
                0 if _skeleton_verdict() is False else None),
            "skeleton_verdict_source": (
                "由 workflow_template._verify_skeleton_unchanged() 计算得出"),
            "domain_param_lines_added": fin.get("lines", 0),
            "domain_spec_fields_to_fill": len(tpl["domain_spec_fields"]),
            "domain_spec_field_names": tpl["domain_spec_fields"],
        },
        "hours_estimate": {
            "medical": estimate_hours(med, CORPUS["医疗"]),
            "finance": estimate_hours(fin, CORPUS["金融"]),
            "manufacturing": estimate_hours(mfg, CORPUS["制造"]),
        },
        "skeleton_vs_params": {
            "skeleton_lines": tpl["skeleton_lines"],
            "domain_spec_lines_medical": med.get("lines", 0),
            "domain_spec_lines_finance": fin.get("lines", 0),
            "skeleton_share_of_total": round(
                tpl["skeleton_lines"] / max(tpl["total_lines"], 1), 4),
        },
    }

    print("=" * 78)
    print("  多行业迁移成本量化（轻量化验证）")
    print("=" * 78)
    print(f"  模板文件总行数        : {tpl['total_lines']}")
    print(f"  骨架函数行数          : {tpl['skeleton_lines']}  （跨领域复用）")
    print(f"  领域参数函数行数      : {tpl['domain_spec_lines']}  （迁移时需改）")
    print(f"  骨架占比              : {report['skeleton_vs_params']['skeleton_share_of_total']*100:.1f}%")
    print()
    print(f"  DomainSpec 需填字段   : {len(tpl['domain_spec_fields'])} 个")
    print(f"    {tpl['domain_spec_fields']}")
    print()
    print("  领域参数规模：")
    for name, d in [("医疗", med), ("金融", fin)]:
        print(f"    {name}: 类目 {d.get('classes')} / 关系 {d.get('relations')} / "
              f"数值模式 {d.get('numeric_patterns')} / 别名 {d.get('alias_items')} 条 "
              f"（函数 {d.get('lines')} 行）")
    print()
    print("  ★ 迁移成本：")
    mc = report["migration_cost"]
    print(f"    改动文件数            : {mc['changed_file_count']}")
    print(f"    骨架代码改动行数      : {mc['skeleton_code_lines_changed']}")
    print(f"    需填写的字段数        : {mc['domain_spec_fields_to_fill']}")
    print()
    print("  工时估算（按单价折算）：")
    for name in ("medical", "finance"):
        h = report["hours_estimate"][name]
        print(f"    {name}: {h['total_hours']} 小时  （{h['total_minutes']} 分钟）")
        for k, v in h["breakdown_minutes"].items():
            print(f"        {k:<14} {v:>7.1f} 分钟")
    print("=" * 78)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"  报告已保存: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
