#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OWL/TTL 本体导出器
================================================================

补齐流水线缺口：`ontology_builder.py --out-ontology` 输出的是**种子本体 JSON**
（供抽取器使用的内部表示），而非标准的 OWL/TTL 文件。

本模块把「种子本体 JSON + 抽取的三元组」导出为**标准 OWL 本体（Turtle 语法）**，
使本体产物可以从流水线完整重现，而非单独手工产出。

导出内容包括：
  · owl:Class 层次结构（含 rdfs:subClassOf）
  · owl:ObjectProperty / owl:DatatypeProperty
  · 条款锚点实例（18 条推荐意见）
  · skos:closeMatch 标准对齐（Lung-RADS / RadLex / SNOMED CT / LOINC / ICD-10）
  · rdfs:comment 溯源注释（条款编号 + 原文要点）

用法：
    python3 ontology_export.py \
        --seed ontology_seed.json \
        --triples triples.json \
        --out lung_nodule_ontology.ttl \
        --report
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from datetime import date


# ============================================================================
# 标准对齐表（外部标准的稳定标识符）
# ============================================================================

# 键为本地概念名，值为 [(标准名, 标识符 URI), ...]
# 注意：同一个概念可对齐到多个标准，因此**不能用 dict 的键去承载多值**
# （早期版本的 bug：dict 字面量里重复键会静默覆盖，导致只保留最后一个对齐）
STANDARD_ALIGNMENTS: list[tuple[str, str, str]] = [
    # (本地概念, 标准名, 标识符 URI)

    # —— ACR Lung-RADS：报告分类体系 ——
    ("肺结节",          "Lung-RADS", "https://www.acr.org/Clinical-Resources/Reporting-and-Data-Systems/Lung-Rads"),
    ("实性肺结节",       "Lung-RADS", "https://www.acr.org/Clinical-Resources/Reporting-and-Data-Systems/Lung-Rads"),
    ("亚实性肺结节",     "Lung-RADS", "https://www.acr.org/Clinical-Resources/Reporting-and-Data-Systems/Lung-Rads"),

    # —— RadLex：放射学术语唯一标识 ——
    ("肺结节",          "RadLex",    "http://radlex.org/RID/RID3870"),
    ("孤立性肺结节",     "RadLex",    "http://radlex.org/RID/RID3874"),
    ("纯磨玻璃结节",     "RadLex",    "http://radlex.org/RID/RID3880"),
    ("混杂性磨玻璃结节",  "RadLex",    "http://radlex.org/RID/RID3881"),

    # —— SNOMED CT：临床医学术语 ——
    ("肺结节",          "SNOMED CT", "http://snomed.info/id/427359001"),
    ("孤立性肺结节",     "SNOMED CT", "http://snomed.info/id/309515003"),
    ("位于上叶",         "SNOMED CT", "http://snomed.info/id/272693004"),

    # —— LOINC：检查项目编码 ——
    ("低剂量CT",        "LOINC",     "http://loinc.org/24604-1"),
    ("薄层CT",          "LOINC",     "http://loinc.org/24604-1"),
    ("胸部增强CT",       "LOINC",     "http://loinc.org/24604-1"),
    ("PET-CT",         "LOINC",     "http://loinc.org/44141-4"),
    ("非手术活检",       "LOINC",     "http://loinc.org/44141-4"),

    # —— ICD-10：疾病分类 ——
    ("肺癌",            "ICD-10",    "http://id.who.int/icd/entity/1635437709"),
]


def _alignments_for(concept: str) -> list[tuple[str, str]]:
    """返回某概念的全部标准对齐（可能多个标准）。"""
    return [(std, uri) for c, std, uri in STANDARD_ALIGNMENTS if c == concept]

# 本体命名空间
NS = "http://nexent.local/ontology/lung-nodule#"
PREFIXES = f"""@prefix : <{NS}> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix dcterms: <http://purl.org/dc/terms/> .
"""


def _q(name: str) -> str:
    """把中文概念名转为安全的 Turtle 局部名。"""
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_\-]*", name):
        return name
    return name  # Turtle 允许中文标识符


def _esc(s: str) -> str:
    """转义 Turtle 字符串字面量。"""
    return (s.replace("\\", "\\\\")
             .replace('"', '\\"')
             .replace("\n", "\\n")
             .replace("\r", ""))


def _load_triples(path: str) -> list[dict]:
    """读取三元组文件。

    兼容两种格式：
      · 标准 JSON 数组  ——  [ {...}, {...} ]
      · JSONL          ——  每行一个 JSON 对象（ontology_builder 的默认输出）
    """
    with open(path, encoding="utf-8") as f:
        head = f.read(1)
        f.seek(0)
        if head == "[":
            obj = json.load(f)
            return obj if isinstance(obj, list) else (obj.get("triples") or [])
        # JSONL
        out: list[dict] = []
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out


def export(seed: dict, triples: list[dict], doc_title: str = "") -> tuple[str, dict]:
    """把种子本体与三元组导出为 Turtle 文本。"""
    out: list[str] = []
    stats = defaultdict(int)

    # ---------- 头部 ----------
    out.append(PREFIXES)
    out.append("")
    out.append("<> a owl:Ontology ;")
    out.append(f'    dcterms:title "{_esc(doc_title or "肺结节规范处置领域本体")}"@zh ;')
    out.append(f'    dcterms:created "{date.today().isoformat()}"^^xsd:date ;')
    out.append('    dcterms:description "面向肺结节规范处置决策的领域本体，'
               '由指南条款半自动化构建，所有类与属性均可溯源至具体推荐意见。"@zh ;')
    out.append('    rdfs:comment "自动生成，请勿手工修改；修改请更新种子本体或抽取规则。"@zh .')
    out.append("")

    classes = seed.get("classes", {})

    # ---------- 类层次 ----------
    out.append("# " + "=" * 68)
    out.append("# 一、类层次结构")
    out.append("# " + "=" * 68)
    out.append("")
    for name, spec in classes.items():
        parent = spec.get("parent")
        out.append(f":{_q(name)} a owl:Class ;")
        if parent:
            out.append(f"    rdfs:subClassOf :{_q(parent)} ;")
        # 别名
        aliases = spec.get("aliases") or []
        if aliases:
            out.append(f'    skos:altLabel "{_esc(" / ".join(aliases))}"@zh ;')
        # 数值约束
        con = spec.get("constraint") or {}
        if con:
            parts = []
            for field, lim in con.items():
                if "min" in lim:
                    parts.append(f"{field} ≥ {lim['min']}")
                if "max" in lim:
                    parts.append(f"{field} ≤ {lim['max']}")
            if parts:
                out.append(f'    rdfs:comment "数值约束：{"；".join(parts)}"@zh ;')
        # 标准对齐
        aligns = _alignments_for(name)
        for std, uri in aligns:
            out.append(f"    skos:closeMatch <{uri}> ;")
            stats[f"align_{std}"] += 1
            stats["alignments"] += 1
        # 收尾：把最后一个 " ;" 换成 " ."
        out[-1] = out[-1].rstrip(" ;") + " ."
        out.append("")
        stats["classes"] += 1
    out.append("")

    # ---------- 属性 ----------
    obj_props: dict[str, str] = {}
    data_props: dict[str, str] = {}
    for t in triples:
        p = t.get("predicate") or t.get("relation") or ""
        if not p:
            continue
        if t.get("kind") == "data":
            data_props.setdefault(p, t.get("unit") or "string")
        else:
            obj_props.setdefault(p, "")

    out.append("# " + "=" * 68)
    out.append("# 二、对象属性")
    out.append("# " + "=" * 68)
    out.append("")
    for p, _ in obj_props.items():
        out.append(f":{_q(p)} a owl:ObjectProperty ;")
        out.append(f'    rdfs:label "{_esc(p)}"@zh .')
        out.append("")
        stats["object_properties"] += 1
    out.append("")

    out.append("# " + "=" * 68)
    out.append("# 三、数据属性")
    out.append("# " + "=" * 68)
    out.append("")
    xsd_map = {"string": "xsd:string", "int": "xsd:integer", "float": "xsd:decimal"}
    for p, unit in data_props.items():
        out.append(f":{_q(p)} a owl:DatatypeProperty ;")
        rng = xsd_map.get(unit, "xsd:string") if unit in xsd_map else "xsd:string"
        out.append(f"    rdfs:range {rng} ;")
        out.append(f'    rdfs:label "{_esc(p)}"@zh .')
        out.append("")
        stats["datatype_properties"] += 1
    out.append("")

    # ---------- 条款锚点 ----------
    out.append("# " + "=" * 68)
    out.append("# 四、条款锚点实例（推荐意见）")
    out.append("# " + "=" * 68)
    out.append("")
    seen: set[str] = set()
    for t in triples:
        cl = t.get("clause") or t.get("clause_number")
        if not cl:
            continue
        m = re.search(r"(\d+)", str(cl))
        if not m:
            continue
        num = m.group(1)
        if num in seen:
            continue
        seen.add(num)
        out.append(f":推荐意见{num} a :推荐意见 ;")
        out.append(f"    :clauseNumber {num} ;")
        title = t.get("clause_title") or ""
        if title:
            out.append(f'    rdfs:label "{_esc(title)}"@zh ;')
        # 推荐强度（从三元组的 strength 字段取，同一条款可能多条三元组）
        strength = t.get("strength") or ""
        if strength:
            out.append(f'    :recommendationStrength "{_esc(strength)}"@zh ;')
        # 条款原文要点（截断，避免本体文件过大）
        ev = (t.get("evidence") or "").strip()
        if ev:
            brief = re.sub(r"\s+", " ", ev)[:180]
            out.append(f'    rdfs:comment "{_esc(brief)}"@zh ;')
        out.append(f'    dcterms:source "{_esc(doc_title)}"@zh .')
        out.append("")
        stats["clause_instances"] += 1

    out.append("")
    out.append("# " + "=" * 68)
    out.append("# 五、溯源说明")
    out.append("# " + "=" * 68)
    out.append("#")
    out.append("# 本体的每个类与属性均可溯源至具体推荐意见条款。")
    out.append("# 实例的三元组关系存放于知识图谱（由 kg_reasoning_service 加载），")
    out.append("# 本文件只描述**概念层**（TBox），不含断言层（ABox）。")
    out.append("#")
    out.append("# 标准对齐来源：")
    out.append("#   · ACR Lung-RADS  https://www.acr.org/Clinical-Resources/Reporting-and-Data-Systems/Lung-Rads")
    out.append("#   · RadLex         http://radlex.org/")
    out.append("#   · SNOMED CT      http://snomed.info/sct")
    out.append("#   · LOINC          http://loinc.org/")
    out.append("#   · ICD-10         https://icd.who.int/")
    out.append("")

    return "\n".join(out), dict(stats)


def main() -> int:
    ap = argparse.ArgumentParser(description="OWL/TTL 本体导出器")
    ap.add_argument("--seed", required=True, help="种子本体 JSON")
    ap.add_argument("--triples", default="", help="抽取的三元组 JSON")
    ap.add_argument("--out", required=True, help="输出 TTL 路径")
    ap.add_argument("--title", default="", help="来源文档标题")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--report-json", default="")
    args = ap.parse_args()

    if not os.path.exists(args.seed):
        print(f"[ERROR] 种子本体不存在: {args.seed}", file=sys.stderr)
        return 2

    with open(args.seed, encoding="utf-8") as f:
        seed = json.load(f)

    triples: list[dict] = []
    if args.triples and os.path.exists(args.triples):
        triples = _load_triples(args.triples)

    ttl, stats = export(seed, triples, args.title)

    with open(args.out, "w", encoding="utf-8") as f:
        f.write(ttl)

    if args.report:
        print("=" * 68)
        print("  OWL 本体导出报告")
        print("=" * 68)
        print(f"  种子本体类数      : {stats.get('classes', 0)}")
        print(f"  对象属性          : {stats.get('object_properties', 0)}")
        print(f"  数据属性          : {stats.get('datatype_properties', 0)}")
        print(f"  条款锚点实例      : {stats.get('clause_instances', 0)}")
        print(f"  skos:closeMatch   : {stats.get('alignments', 0)}")
        for k, v in sorted(stats.items()):
            if k.startswith("align_"):
                print(f"    ├─ {k[6:]:14s} {v}")
        print("-" * 68)
        print(f"  输出文件          : {args.out}  ({os.path.getsize(args.out):,} 字节)")
        print("=" * 68)

    if args.report_json:
        with open(args.report_json, "w", encoding="utf-8") as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)

    return 0


if __name__ == "__main__":
    sys.exit(main())
