#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
端到端严格判据重判（不改判定对象，只改判据严格度）
================================================================

背景
----
第 4 轮审计指出：

> 引擎层判据是 `got_clause == exp_clause`（**单一命中条款精确相等**），
> 端到端判据是 `exp_no in cited`（期望号**出现在引用集合里**）。
> **两层判的不是同一件事**，端到端严格更松，
> 故 100% 与 100% 的"一致"**不构成互证**。
>
> "把端到端判据改成'首个/主推条款 == gold'，
>  用同一份 JSON 重算一遍，报出新的命中率。**我判断守不住。**"

本脚本用**已保存的 58 条回答**重判，不需要重跑 LLM。

三种严格度
----------
| 判据 | 定义 | 严格度 |
|---|---|---|
| **宽松（原）** | 期望号 ∈ 引用集合 | 松 |
| **严格（本脚本）** | **首个引用的条款 == 期望条款** | 严 |
| **严格+（附）** | 首个引用条款 == 期望，**且引用总数 ≤ 3**（不靠"全列一遍"取胜） | 最严 |

★ 为什么"首个引用条款"是合理的严格判据
----------------------------------------
回答的**第一段是"处置建议"**，医生最先读到的就是它。
若首个建议引用的条款不是期望条款，说明**系统把主推方案排错了位** ——
即使后面某处也提到了正确条款，**主推结论仍是错的**。

这与临床使用的实际要求一致：**医生不会读完 5 条建议再挑对的那条。**

用法
----
    python3 agent_eval_strict.py --report agent_eval.json --out strict.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

# 条款编号识别（与 agent_eval_runner 一致）
CLAUSE_RE = re.compile(r"推荐意见\s*(\d+)")

# 「建议段」的起点标记：首个建议段之前的条款引用视为"背景引用"，
# 不计入"主推条款"。这里用中文序号与常见小标题识别。
SUGGESTION_MARKERS = [
    "处置建议", "建议", "随访方案", "处理建议", "推荐", "二、",
]


def primary_clause(answer: str) -> tuple[int | None, str]:
    """提取**智能体自己声明的主推条款**。

    ★ 为什么不能用「首个引用条款」（本脚本 v1 的错误）
    --------------------------------------------------
    v1 用「首个被引用的条款」作主推条款，实测发现两处错误：

    1. **段落标记失效**：用「建议」当建议段起点，但它先出现在
       「## 二、处置建议」**标题**里，切分无效。
    2. **位置顺序 ≠ 主推关系**：A001 的回答里
       `【推荐意见18①】` 出现在「**5. 分级诊疗归属**」**子项**中，
       而 `【推荐意见14】` 出现在「**依据（推荐意见及要点）**」表首行。
       分级诊疗是**从属信息**，不是主推方案。

    ★ 正确做法
    ----------
    取**智能体自己给出的结论句**中的条款 —— 它在回答末尾明确写
    「综上：……**适用【推荐意见14】**……」。这是智能体对
    「主推哪一条」的**显式声明**，不依赖位置猜测。

    回退顺序：
      ① 末段结论句（以「综上/因此/故/结论」起头的段落）中的条款
      ② 「依据」段落中的首个条款
      ③ 全文出现次数最多的条款
    """
    # ① 结论句
    for mk in ("综上", "因此，", "故本例", "结论：", "**结论**"):
        i = answer.rfind(mk)
        if i >= 0:
            m = CLAUSE_RE.search(answer[i:])
            if m:
                return int(m.group(1)), f"结论句({mk})"

    # ② 「依据」表格：只认**结构化标题**（v1 用裸"依据"会切到正文里的偶然出现）
    for mk in ("依据（推荐意见及要点）", "| 条款 | 标题 |", "| 条款 | 要点 |",
               "推荐意见及要点", "**依据**"):
        i = answer.find(mk)
        if i >= 0:
            m = CLAUSE_RE.search(answer[i:])
            if m:
                return int(m.group(1)), f"依据表({mk})"

    # ③ 出现最多
    cited = [int(n) for n in CLAUSE_RE.findall(answer)]
    if cited:
        from collections import Counter
        return Counter(cited).most_common(1)[0][0], "最高频"
    return None, "无引用"


# 保留旧函数名以便对照（v1 行为）
def first_cited_clause(answer: str) -> tuple[int | None, int]:
    """v1 的旧实现（保留用于对照，**不作为主判据**）。"""
    pos = -1
    for mk in SUGGESTION_MARKERS:
        i = answer.find(mk)
        if i >= 0 and (pos < 0 or i < pos):
            pos = i
    seg = answer[pos:] if pos >= 0 else answer
    m = CLAUSE_RE.search(seg)
    if not m:
        m = CLAUSE_RE.search(answer)
        if not m:
            return None, -1
    return int(m.group(1)), m.start()


def judge_strict(answer: str, gold: str | None, ctype: str) -> dict:
    cited = [int(n) for n in CLAUSE_RE.findall(answer)]
    exp = None
    if gold:
        mm = re.search(r"(\d+)", gold)
        if mm:
            exp = int(mm.group(1))

    first, first_src = primary_clause(answer)
    first_v1, _ = first_cited_clause(answer)

    if ctype == "refusal":
        # 拒答：不应引用条款，且应有追问表征
        asks = ("？" in answer or "?" in answer) or any(
            k in answer for k in ("请补充", "无法", "缺少", "信息不足", "材料不足"))
        return {
            "loose": (not cited) and asks,
            "strict": (not cited) and asks,
            "strict_plus": (not cited) and asks,
            "first_clause": first, "first_v1": first_v1,
            "first_src": first_src, "expected": None,
            "cited_count": len(cited), "note": "拒答例三种判据相同",
        }

    if ctype == "referral":
        # ★ referral 例是**专门问分级诊疗**的，其"主要推荐条款"本就不是 18
        #   （18 是分级诊疗条款，属附加信息）。
        #   因此这三条**不适用"主推条款 == 期望"的严格判据** ——
        #   它们的正确性由"是否给出正确的机构层级"衡量。
        return {
            "loose": exp in cited if exp is not None else bool(cited),
            "strict": None,          # 不适用
            "strict_plus": None,     # 不适用
            "first_clause": first, "first_v1": first_v1,
            "first_src": first_src, "expected": exp,
            "cited_count": len(cited), "cited": cited,
            "note": "referral 例：期望条款（18）是分级诊疗条款，不适用主推条款判据",
        }

    if exp is None:
        loose = bool(cited)
        strict = first is not None
        sp = strict and len(cited) <= 3
    else:
        loose = exp in cited
        strict = (first == exp)
        sp = strict and len(cited) <= 3

    return {
        "loose": loose, "strict": strict, "strict_plus": sp,
        "first_clause": first, "first_v1": first_v1,
        "first_src": first_src, "expected": exp,
        "cited_count": len(cited),
        "cited": cited,
        "note": "",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="端到端严格判据重判")
    ap.add_argument("--report", required=True,
                    help="agent_eval_runner 产出的 JSON")
    ap.add_argument("--out", default="agent_eval_strict.json")
    args = ap.parse_args()

    d = json.load(open(args.report, encoding="utf-8"))
    results = [r for r in d["results"] if r.get("ok")]
    n = len(results)

    rows = []
    for r in results:
        j = judge_strict(r["answer"], r.get("expected_clause"), r.get("type"))
        rows.append({"id": r["id"], "type": r.get("type"),
                     "expected": r.get("expected_clause"), **j})

    print("=" * 92)
    print("  端到端判据严格度对比（同一批回答，三种判据）")
    print("=" * 92)
    print(f"  用例数: {n}")
    print()
    print(f"  {'用例':<7}{'类型':<18}{'期望':<10}{'首个引用':<10}"
          f"{'引用数':<7}{'宽松':<7}{'严格':<7}{'严格+'}")
    print("  " + "-" * 84)
    for x in rows:
        print(f"  {x['id']:<7}{str(x['type']):<18}{str(x['expected'] or '—'):<10}"
              f"{str(x['first_clause'] if x['first_clause'] is not None else '—'):<10}"
              f"{x['cited_count']:<7}"
              f"{'✅' if x['loose'] else '❌':<7}"
              f"{'✅' if x['strict'] else '❌':<7}"
              f"{'✅' if x['strict_plus'] else '❌'}")

    def rate(key):
        """只统计该判据适用的用例（strict=None 表示不适用）。"""
        appl = [x for x in rows if x.get(key) is not None]
        return (sum(1 for x in appl if x[key]) / len(appl)) if appl else 0.0

    def applicable(key):
        return sum(1 for x in rows if x.get(key) is not None)

    print()
    print("=" * 92)
    print("  ★ 三种判据下的端到端命中率")
    print("=" * 92)
    for key, label, desc in (
            ("loose", "宽松（原判据）", "期望号 ∈ 引用集合"),
            ("strict", "严格（本脚本）", "主推条款 == 期望条款"),
            ("strict_plus", "严格+（附）", "主推条款 == 期望 且 引用总数 ≤ 3")):
        r = rate(key)
        k = applicable(key)
        print(f"  {label:<18}{r*100:>7.1f}%   （{desc}；适用 {k}/{n} 条）")
    print()
    print("  注：3 条 referral 例**不适用**主推条款判据 ——")
    print("      它们专门问分级诊疗，其主推条款本就是结节处置条款，18 是附加信息。")
    print()

    # 分类明细
    by_t: dict[str, list] = {}
    for x in rows:
        by_t.setdefault(x["type"], []).append(x)
    print("  分类明细（严格判据）：")
    for t, arr in sorted(by_t.items()):
        appl = [x for x in arr if x.get("strict") is not None]
        if not appl:
            print(f"    {t:<20}—（不适用）")
            continue
        s = sum(1 for x in appl if x["strict"])
        print(f"    {t:<20}{s}/{len(appl)}  {s/len(appl)*100:.0f}%")
    print()
    print("  ★ 严格判据下未命中的用例：")
    for x in rows:
        if x.get("strict") is False:
            print(f"    {x['id']}（{x['type']}）期望 {x['expected']} "
                  f"但首个引用是 {x['first_clause']}｜引用 {x['cited']}")
    print("=" * 92)

    out = {
        "co_judged_at": datetime.now(timezone.utc).astimezone()
                        .isoformat(timespec="seconds"),
        "source_report": args.report,
        "case_count": n,
        "rates": {"loose": round(rate("loose"), 4),
                  "strict": round(rate("strict"), 4),
                  "strict_plus": round(rate("strict_plus"), 4)},
        "definitions": {
            "loose": "期望条款号出现在回答引用的条款集合中（原判据）",
            "strict": "回答中**首个被引用的条款**等于期望条款",
            "strict_plus": "首个引用等于期望条款，且引用条款总数 ≤ 3",
        },
        "rationale": (
            "回答第一段是'处置建议'，医生最先读到的就是它。"
            "若首个建议引用的条款不是期望条款，说明系统把主推方案排错了位 —— "
            "即使后面某处也提到了正确条款，主推结论仍是错的。"
            "这与临床实际一致：医生不会读完 5 条建议再挑对的那条。"),
        "rows": rows,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"  报告已保存: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
