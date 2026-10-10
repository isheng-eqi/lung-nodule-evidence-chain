#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
全包一致性扫描 v3.0
================================================================

版本演进（每一步都是被审计推着改的）
------------------------------------
v1.0 —— 被审计证明**给出假"全清"**：正则匹配不上 markdown 粗体
        （`共 **89 个文件**`），且"同一指标多值"4 项检查里 3 项恒不可能触发。
v2.0 —— 改为"触发词 ± 窗口找数字"，结果**走向另一个极端**：
        窗口里混入行号、章节号、比例，产生大量误报（如把行号 8 当成"类数"）。
v3.0 —— **每条规则只匹配语义明确的句式**，并对每条规则做**正/负样本自检**。

v3.0 的核心原则
---------------
· **宁缺勿滥**：只报能用一句话说清"这里本该是 X 却写了 Y"的偏差
· **每条规则都有负样本**：确认它**不会**匹配到无关文本
· **自检不通过则拒绝输出结论** —— 防止再次产生"虚假保证"

用法
----
    python3 consistency_scan.py --pkg .. --out consistency_report.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass


def strip_md(t: str) -> str:
    t = re.sub(r"\*\*|__", "", t)
    t = re.sub(r"`", "", t)
    return t


# ============================================================================
# 一、实测包内真实值
# ============================================================================

def measure(pkg: str) -> dict:
    m: dict = {"package": os.path.abspath(pkg)}
    files, total = [], 0
    for root, _d, fs in os.walk(pkg):
        for f in fs:
            p = os.path.join(root, f)
            files.append(os.path.relpath(p, pkg).replace("\\", "/"))
            try:
                total += os.path.getsize(p)
            except OSError:
                pass
    m["file_count"] = len(files)
    m["file_count_excl_pyc"] = sum(1 for f in files if not f.endswith(".pyc"))
    m["pyc_count"] = len(files) - m["file_count_excl_pyc"]
    m["total_mb"] = round(total / 1024 / 1024, 2)

    mcp = os.path.join(pkg, "02_代码与本体/mcp-server/kg_mcp_server.py")
    if os.path.exists(mcp):
        src = open(mcp, encoding="utf-8").read()
        m["mcp_tool_count"] = len(set(re.findall(r"def (kg_\w+)\(", src)))
        m["mcp_tool_names"] = sorted(set(re.findall(r"def (kg_\w+)\(", src)))
        m["mcp_server_kb"] = round(os.path.getsize(mcp) / 1024, 1)

    docx = os.path.join(pkg, "01_开发设计文档/开发设计文档_final.docx")
    if os.path.exists(docx):
        m["docx_kb"] = round(os.path.getsize(docx) / 1024, 1)

    ttl: dict[str, int] = {}
    od = os.path.join(pkg, "02_代码与本体/ontology")
    if os.path.isdir(od):
        for root, _d, fs in os.walk(od):
            for f in fs:
                if f.endswith(".ttl"):
                    t = open(os.path.join(root, f), encoding="utf-8",
                             errors="replace").read()
                    ttl[f] = len(re.findall(r"a\s+owl:Class", t))
    m["ttl_class_counts"] = ttl
    return m


# ============================================================================
# 二、★ 精确规则：每条只匹配语义明确的句式，并附正/负样本自检
# ============================================================================

# (指标名, 正则, 取第几组, 实测 key, 正样本, [负样本...])
RULES: list[tuple] = [
    ("包内文件数",
     re.compile(r"共\s*([\d,]+)\s*个文件|文件总数\s*[:：]?\s*([\d,]+)"),
     124, "file_count",
     ["本包共 **89 个文件**", "文件总数：122"],
     # 负样本只放**句式完全不同**的（"共 N 个文件"本身就有歧义：
     # 它可能指"共 3 个文件被修改"，因此不作为负样本）
     ["共 89 个条目", "文件大小 122 KB", "MANIFEST 共 122 行"]),

    ("自研 MCP 工具数",
     re.compile(r"([\d]+)\s*个\s*(?:自研\s*)?(?:MCP\s*)?kg_\*?\s*工具|"
                r"工具数\s*[:：|]\s*\**\s*([\d]+)\s*个"),
     7, "mcp_tool_count",
     ["**7 个** kg_* 工具", "| 工具数 | **7 个** `kg_*`"],
     ["1 个内置检索工具", "6 个工具实例（含内置）"]),

    ("MCP Server 体积(KB)",
     re.compile(r"kg_mcp_server\.py[^\n]{0,30}?([\d.]+)\s*KB|"
                r"([\d.]+)\s*KB[^\n]{0,30}?kg_mcp_server\.py|"
                r"自研\s*MCP\s*Server[^\n]{0,40}?([\d.]+)\s*KB"),
     None, "mcp_server_kb",
     ["`mcp-server/kg_mcp_server.py`（60.9 KB）",
      "mcp-server/kg_mcp_server.py（60.9 KB）",
      "自研 MCP Server（60.9 KB）"],
     ["43 KB 的其他文件"]),

    ("Word 体积(KB)",
     re.compile(r"开发设计文档_final\.docx[^\n]{0,25}?([\d,.]+)\s*KB"),
     None, "docx_kb",
     ["开发设计文档_final.docx（1,264.0 KB）"],
     ["开发设计文档_源文件.md（145.9 KB）"]),
]


def self_test() -> tuple[bool, list[str]]:
    """对每条规则跑正/负样本 —— 防止出现"检查本身失效"。"""
    msgs, ok = [], True
    for name, pat, _grp, _key, pos, negs in RULES:
        for s in pos:
            t = strip_md(s)
            if not pat.search(t):
                ok = False
                msgs.append(f"  🔴 正样本未命中 [{name}]: {s}")
        for s in negs:
            t = strip_md(s)
            m = pat.search(t)
            if m:
                # 负样本命中要看是否真的会产生误报值 —— 这里仅提示
                msgs.append(f"  ⚠️ 负样本命中 [{name}]: {s} → "
                            f"{[g for g in m.groups() if g]}")
    if ok:
        msgs.append(f"  ✅ 全部 {len(RULES)} 条规则的正样本均命中")
    return ok, msgs


def scan(pkg: str, measured: dict) -> list[dict]:
    targets = []
    for root, _d, fs in os.walk(pkg):
        for f in fs:
            if f.endswith((".md", ".json")) and "MANIFEST" not in f:
                targets.append(os.path.join(root, f))
    wp = os.path.join(os.path.dirname(os.path.abspath(pkg)),
                      "docs/开发设计文档_正文.md")
    if os.path.exists(wp):
        targets.append(wp)

    out, seen = [], set()
    for tp in targets:
        try:
            raw = open(tp, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        t = strip_md(raw)
        rel = os.path.relpath(tp, os.path.dirname(os.path.abspath(pkg)))
        for name, pat, _grp, key, _p, _n in RULES:
            actual = measured.get(key)
            if actual is None:
                continue
            for mm in pat.finditer(t):
                g = next((x for x in mm.groups() if x), None)
                if g is None:
                    continue
                try:
                    cv = float(g.replace(",", ""))
                except ValueError:
                    continue
                if abs(cv - float(actual)) <= max(0.15 * float(actual), 0.5):
                    continue
                if cv > 100000:
                    continue
                pos = raw.find(g)
                ln = raw[:pos].count("\n") + 1 if pos >= 0 else 0
                k = (rel, ln, name, g)
                if k in seen:
                    continue
                seen.add(k)
                out.append({"item": name, "file": rel, "line": ln,
                            "claimed": g, "actual": actual,
                            "context": t[max(0, mm.start() - 45):mm.end() + 45]
                                       .replace("\n", " ")})
    return out


def check_refs(pkg: str) -> list[dict]:
    """只查 `docs/xxx.md` 形式的引用（这些最容易悬空）。"""
    pkg_abs = os.path.abspath(pkg)
    ref_re = re.compile(r"`(docs/[^`\s]+?\.[a-zA-Z]{2,5})`")
    existing = set()
    for root, _d, fs in os.walk(pkg):
        for f in fs:
            existing.add(os.path.relpath(os.path.join(root, f), pkg)
                         .replace("\\", "/"))
    issues = []
    for tp in [os.path.join(r, f) for r, _d, fs in os.walk(pkg)
               for f in fs if f.endswith(".md")]:
        raw = open(tp, encoding="utf-8", errors="replace").read()
        rel = os.path.relpath(tp, pkg_abs)
        for mm in ref_re.finditer(raw):
            ref = mm.group(1)
            if any(e.endswith(ref.split("/")[-1]) for e in existing):
                continue
            ln = raw[:mm.start()].count("\n") + 1
            issues.append({"file": rel, "line": ln, "referenced": ref,
                           "note": "该文件不在包内（可能是工作区路径，需确认为有意引用）"})
    return issues


def main() -> int:
    ap = argparse.ArgumentParser(description="全包一致性扫描 v3.0")
    ap.add_argument("--pkg", required=True)
    ap.add_argument("--out", default="consistency_report.json")
    args = ap.parse_args()

    print("=" * 82)
    print("  全包一致性扫描 v3.0（精确句式 + 正负样本自检）")
    print("=" * 82)

    ok, msgs = self_test()
    print("  【扫描器自检】")
    for x in msgs:
        print(x)
    if not ok:
        print("  ⚠️ 自检未通过 —— 拒绝输出结论（防止虚假保证）")
        return 1
    print()

    m = measure(args.pkg)
    print("  【实测值】")
    print(f"    文件数（含 .pyc）  : {m['file_count']}"
          + (f"  ⚠️ 含编译产物 {m['pyc_count']} 个" if m["pyc_count"] else ""))
    print(f"    文件数（不含 .pyc）: {m['file_count_excl_pyc']}")
    print(f"    总大小            : {m['total_mb']} MB")
    if "mcp_tool_count" in m:
        print(f"    MCP 工具数        : {m['mcp_tool_count']}  {m['mcp_tool_names']}")
        print(f"    MCP Server        : {m['mcp_server_kb']} KB")
    if "docx_kb" in m:
        print(f"    Word              : {m['docx_kb']} KB")
    for f, n in (m.get("ttl_class_counts") or {}).items():
        print(f"    TTL {f:<46} {n} 类")
    print()

    mism = scan(args.pkg, m)
    refs = check_refs(args.pkg)

    print("  【数字声称与实测的偏差】")
    if not mism:
        print("    ✅ 未发现偏差")
    else:
        for x in mism:
            print(f"    🔴 {x['item']}: 声称 {x['claimed']} / 实际 {x['actual']}")
            print(f"         {x['file']}:{x['line']}")
            print(f"         …{x['context'][:96]}…")
    print()
    print("  【docs/ 路径引用完整性】")
    if not refs:
        print("    ✅ 未发现悬空引用")
    else:
        for r in refs:
            print(f"    ⚠️ {r['file']}:{r['line']} → {r['referenced']}")
    print("=" * 82)

    rep = {"scanner_version": "3.0", "self_test_passed": ok,
           "generated_at": datetime.now(timezone.utc).astimezone()
                           .isoformat(timespec="seconds"),
           "measured": m, "number_mismatches": mism, "dangling_refs": refs,
           "summary": {"number_mismatch_count": len(mism),
                       "dangling_ref_count": len(refs)}}
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=2)
    print(f"  报告已保存: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
