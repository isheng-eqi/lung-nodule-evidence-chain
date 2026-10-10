#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""数值注入器：把 JSON 实测值写回正文表格，终结"表格 vs JSON"反复分叉。

★ 为什么需要这个工具（根因，来自第 68 轮的观察）
================================================

本项目里"文档表格数值 vs 其引用的 JSON"这类矛盾**反复复发**：

| 轮次 | 症状 | 根因 |
|---|---|---|
| 第 60 轮 | 两份 JSON 的 `skeleton_changed` 相反 | 一处硬编码 |
| 第 65 轮 | 两份报告再度相反 | `bool(None)` 丢失三态 |
| 第 68 轮 | 正文表格（278/150/0）vs JSON（1120/662/null） | **表格数值是手工抄的** |

**共同根因**：**数值在多处被手工复制，只要有一处代码改动就会分叉。**

**本工具是那个根因的解法**：表格里的数值不再手写，而是由 JSON 在
**生成流程中注入**。每次 `rebuild_doc` 都会先跑本工具，
因此**表格永远等于 JSON**，无法再分叉。

用法
----
    python3 inject_metrics.py --doc <正文.md> --json <报告.json> [--check]

`--check` 只报告差异、不写文件（用于 CI 式的验证）。

设计原则
--------
· **幂等**：可重复运行，结果稳定 —— 因为它按"样式"重写整行，
  而不是做文本替换累积。
· **保守**：任何一条匹配不到就**打印警告但不中断**，
  因为文档可能在演进；由人来判断是"表格被删了"还是"样式改了"。
"""
from __future__ import annotations

import argparse
import json
import re
import sys


def _g(d: dict, path: str):
    """按点路径取值，支持 `a.b[0].c`。"""
    cur = d
    for part in path.split("."):
        m = re.match(r"^(\w+)(?:\[(\d+)\])?$", part)
        if not m:
            raise KeyError(f"bad path segment: {part}")
        key, idx = m.group(1), m.group(2)
        cur = cur[key]
        if idx is not None:
            cur = cur[int(idx)]
    return cur


# ---------------------------------------------------------------------------
# 注入规则：(说明, 匹配该行的正则, 输出该行的函数)
# ---------------------------------------------------------------------------
def build_rules(report: dict):
    tpl = report["template_analysis"]
    ds = report["domain_specs"]
    he = report["hours_estimate"]
    mc = report["migration_cost"]

    share = tpl["skeleton_lines"] / tpl["total_lines"] * 100

    def n(v):
        return f"{v:,}" if isinstance(v, int) else str(v)

    # ★★ 规则必须**互斥**，否则后写的表会被先命中的规则覆盖。
    #
    # 实测教训：`领域参数-医疗` 的模式 `^\| 医疗（肺结节）\|` **同时匹配了工时表**，
    # 于是工时的 3 列行会被改写成领域参数的 6 列行 —— **把一张表写坏**。
    # 两条规则的首列完全相同，只能靠**行尾形态**区分：
    #   · 领域参数表：以 `| <数字> |` 结尾（参数函数行数）
    #   · 工时表    ：以 `| **<数字> 小时** | … |` 结尾
    # 因此模式里必须**断言行尾**。
    TAIL_PARAM = r"\s*\|\s*\d+\s*\|\s*$"          # 领域参数表行尾
    TAIL_HOURS = r"\s*\|\s*\*\*[\d.]+\s*小时\*\*\s*\|.*\|\s*$"  # 工时表行尾

    rules = [
        # ---- 表 1：模板实测 ----
        ("模板文件总行数",
         r"^\|\s*模板文件总行数\s*\|",
         lambda: f"| 模板文件总行数 | {n(tpl['total_lines'])} |"),
        ("骨架函数行数",
         r"^\|\s*骨架函数行数\s*\|",
         lambda: (f"| 骨架函数行数 | **{n(tpl['skeleton_lines'])}**"
                  f"（跨领域复用，占 **{share:.1f}%**） |")),
        ("领域参数函数行数",
         r"^\|\s*领域参数函数行数\s*\|",
         lambda: (f"| 领域参数函数行数 | **{n(tpl['domain_spec_lines'])}**"
                  f"（迁移时需改） |")),
        ("改动文件数",
         r"^\|\s*\*\*改动文件数\*\*\s*\|",
         lambda: (f"| **改动文件数** | **{mc['changed_file_count']}**"
                  f"（只改 `build_<domain>_spec`，其余文件不动） |")),

        # ---- 表 2：领域参数规模 ----
        # ★ 用「领域名 + 该领域的别名条数」作锚点区分两张表。
        #   为什么不靠行尾：实测 `re.match(前缀 + TAIL_PARAM)` 会失配
        #   （`[^|]*` 与 `.*?` 都会吃掉部分 `|`，而 `TAIL_PARAM` 又要求一个 `|` 起始）。
        #   改用表格里**独有的中间值**（17 / 41 / 40 条）作锚 —— 简单且验证有效。
        ("领域参数-医疗",
         r"^\|\s*医疗.*?17 条\s*\|\s*\d+\s*\|\s*$",
         lambda: (f"| 医疗（肺结节） | {ds['medical']['classes']} | "
                  f"{ds['medical']['relations']} | "
                  f"{ds['medical']['numeric_patterns']} | "
                  f"{ds['medical']['alias_items']} 条 | "
                  f"{ds['medical']['lines']} |")),
        ("领域参数-金融",
         r"^\|\s*金融.*?41 条\s*\|\s*\d+\s*\|\s*$",
         lambda: (f"| 金融（固定资产贷款） | {ds['finance']['classes']} | "
                  f"{ds['finance']['relations']} | "
                  f"{ds['finance']['numeric_patterns']} | "
                  f"{ds['finance']['alias_items']} 条 | "
                  f"{ds['finance']['lines']} |")),
        ("领域参数-制造",
         r"^\|\s*\*{0,2}制造.*?40 条\*{0,2}\s*\|\s*\*{0,2}\d+\*{0,2}\s*\|\s*$",
         lambda: (f"| **制造（特种设备安全）** | **{ds['manufacturing']['classes']}** | "
                  f"**{ds['manufacturing']['relations']}** | "
                  f"**{ds['manufacturing']['numeric_patterns']}** | "
                  f"**{ds['manufacturing']['alias_items']} 条** | "
                  f"**{ds['manufacturing']['lines']}** |")),
    ]

    # ---- 表 3：工时（三种样式都可能，按"领域 + 小时数"识别）----
    for dom, label in (("medical", "医疗（肺结节）"),
                       ("finance", "金融（固定资产贷款）"),
                       ("manufacturing", "制造（特种设备安全）")):
        hrs = he[dom]["total_hours"]

        def mk(lbl: str, h: float, bold: bool):
            def f():
                L = f"**{lbl}**" if bold else lbl
                return f"| {L} | **{h:.2f} 小时** | 定义类目 + 录入别名 + 准备语料 |"
            return f

        rules.append((f"工时-{dom}",
                      rf"^\|\s*\*{{0,2}}{re.escape(label)}\*{{0,2}}\s*\|\s*\*\*[\d.]+\s*小时\*\*\s*\|",
                      mk(label, hrs, dom == "manufacturing")))
    return rules


def main() -> int:
    ap = argparse.ArgumentParser(description="把 JSON 实测值注入正文表格")
    ap.add_argument("--doc", required=True, help="正文 markdown 路径")
    ap.add_argument("--json", required=True, help="量化报告 JSON 路径")
    ap.add_argument("--check", action="store_true",
                    help="只报告差异，不写文件")
    args = ap.parse_args()

    report = json.load(open(args.json, encoding="utf-8"))
    rules = build_rules(report)

    lines = open(args.doc, encoding="utf-8").read().split("\n")
    out: list[str] = []
    hits: dict[str, int] = {name: 0 for name, _p, _f in rules}
    changed: list[tuple[int, str, str]] = []

    for i, line in enumerate(lines, 1):
        replaced = False
        for name, pat, fn in rules:
            if re.match(pat, line):
                hits[name] += 1
                new = fn()
                if new != line:
                    changed.append((i, line, new))
                out.append(new)
                replaced = True
                break
        if not replaced:
            out.append(line)

    print("=" * 78)
    print("  数值注入器 · 把 JSON 实测值写回正文表格")
    print("=" * 78)
    print(f"  正文  : {args.doc}")
    print(f"  JSON  : {args.json}")
    print()
    print("  【规则命中】")
    for name, _p, _f in rules:
        mark = "OK " if hits[name] else "-- "
        print(f"    {mark}{name}: 命中 {hits[name]} 行")
    miss = [n_ for n_, c in hits.items() if c == 0]
    print()
    if miss:
        print(f"  ⚠️ 有 {len(miss)} 条规则未命中（文档可能已演进，请人工确认）")
    print(f"  【数值变更】 {len(changed)} 行")
    for ln, old, new in changed:
        print(f"    L{ln}")
        print(f"      旧: {old.strip()[:100]}")
        print(f"      新: {new.strip()[:100]}")

    if not changed:
        print("\n  ✅ 全部一致 —— 表格数值与 JSON 相同，无需修改")

    if args.check:
        print("\n  （--check 模式：未写入文件）")
        return 0 if not changed else 1

    if changed:
        open(args.doc, "w", encoding="utf-8", newline="\n").write("\n".join(out))
        print(f"\n  ✅ 已写回 {args.doc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
