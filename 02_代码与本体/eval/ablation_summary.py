#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
消融实验 · C 配置（仅图谱）+ 三配置汇总
================================================================

三个配置
--------
**A. 双驱动（完整系统）**
    图谱推理定位条款 + 条目回检原文 =
    `run_inference()` 完整输出（含 contraindications / referral / disambiguation）

**B. 仅检索（RAG-only）**
    见 `ablation_rag_vs_kg.py`：ES 向量检索 top-k 条文 → LLM 作答

**C. 仅图谱（KG-only）**
    走 `run_inference()`，但**L3 证据层失效** —— 即：
      · 不携带条文原文（`caveat` 视为不可得）
      · 不回检 `knowledge_base_search`
    这模拟"图谱能定位条款，但拿不到条款原文"的降级状态。

**为什么 C 是合理的对照**：本项目的 L3 证据层职责是"回检条文原文，补齐表述"。
去掉它，输出的**结论可能仍对，但可核验性下降**（医生看不到条文原文）。
这正是"双驱动"另一半的价值所在。

输出
----
三配置对照表（条款命中率 / 条款级引用率 / 拒答正确率 / 信息不足时的行为）。

用法
----
    python3 eval/ablation_summary.py --rag ablation.json --out ablation_all.json
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys


def load_kg(path: str):
    spec = importlib.util.spec_from_file_location("kgmod", path)
    m = importlib.util.module_from_spec(spec)
    sys.modules["kgmod"] = m          # dataclass 需要模块已注册
    spec.loader.exec_module(m)
    return m


# v1.1 修正：原正则只认全角方括号「【推荐意见N】」，
# 导致基线模型写「（推荐意见15）」时被判为"未引用" —— 这是**测量假阴性**，
# 使 B 配置的条款命中率被系统性低估（3 个场景里吃掉 1 个）。
# 现扩展为接受三类写法：全角方括号 / 圆括号 / 裸写。
CLAUSE_RE = re.compile(
    r"(?:【|（|\(|\[)?\s*推荐意见\s*(\d+)\s*(?:】|）|\)|\])?")

# 与 B 配置完全相同的场景（保证可比）
SCENARIOS = [
    ("A001", "55岁男性，8mm混合磨玻璃结节，实性成分2mm，吸烟30年，该怎么随访？",
     "推荐意见14", "advice"),
    ("A005", "62岁男性，15mm混杂性磨玻璃结节，实性成分6mm，有毛刺征，该如何处理？",
     "推荐意见15", "advice"),
    ("A009", "48岁女性，6mm纯磨玻璃结节，无吸烟史，该如何处理？",
     "推荐意见13", "advice"),
    ("C001", "我有肺结节，该怎么办？", None, "refusal"),
    ("C002", "发现肺部有个影子，需要处理吗？", None, "refusal"),
]


def run_config_A(kg, q: str) -> dict:
    """A 配置：双驱动（完整 run_inference）。"""
    r = kg.run_inference(q)
    # 组织成与 B 配置可比的"回答文本"
    parts = [r.get("conclusion", "")]
    for rec in r.get("recommendations", []):
        parts.append(f"{rec['action']}【{rec['clause']}】")
    if r.get("follow_up"):
        parts.append(f"随访：{r['follow_up']}【{r.get('clause','')}】")
    for c in r.get("contraindications", []):
        parts.append(f"禁忌：{c['reason']}【{c['clause']}】")
    if r.get("referral"):
        parts.append(f"分级诊疗：{r['referral']}")
    return {
        "answer": "\n".join(p for p in parts if p),
        "coverage": r.get("coverage"),
        "clause": r.get("clause"),
        "chain_len": len(r.get("chain", [])),
        "has_caveat_text": bool(r.get("caveat")),
        "has_contraindications": bool(r.get("contraindications")),
        "has_referral": bool(r.get("referral")),
    }


def run_config_C(kg, q: str) -> dict:
    """C 配置：仅图谱（L3 证据层失效 —— 不携带条文原文/边界提示）。"""
    r = kg.run_inference(q)
    parts = [r.get("conclusion", "")]
    for rec in r.get("recommendations", []):
        parts.append(f"{rec['action']}【{rec['clause']}】")
    if r.get("follow_up"):
        parts.append(f"随访：{r['follow_up']}【{r.get('clause','')}】")
    # ★ 关键差异：不输出 contraindications（那来自条文回检）与 caveat
    return {
        "answer": "\n".join(p for p in parts if p),
        "coverage": r.get("coverage"),
        "clause": r.get("clause"),
        "chain_len": len(r.get("chain", [])),
        "has_caveat_text": False,      # L3 失效
        "has_contraindications": False,  # L3 失效
        "has_referral": bool(r.get("referral")),
    }


def analyze(answer: str, gold: str | None, ctype: str) -> dict:
    t = answer or ""
    cited = sorted(set(CLAUSE_RE.findall(t)), key=int)
    gold_num = None
    if gold:
        m = re.search(r"(\d+)", gold)
        gold_num = m.group(1) if m else None
    refused = bool(re.search(
        r"依据不足|无法回答|不能确定|缺少|请.{0,6}(补充|提供)|需要.{0,6}(补充|提供)|信息不足|未覆盖",
        t))
    gave_advice = bool(re.search(r"随访|复查|手术|切除|活检|转诊|个月", t))
    return {
        "answer_chars": len(t),
        "clauses_cited": cited,
        "citation_count": len(cited),
        "has_clause_citation": len(cited) > 0,
        "hit_gold": (gold_num in set(cited)) if gold_num else None,
        "self_declared_insufficient": refused,
        "gave_advice": gave_advice,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="C 配置 + 三配置汇总")
    ap.add_argument("--kg", default="/tmp/kg_mcp_server.py")
    ap.add_argument("--rag", default="ablation.json",
                    help="B 配置的结果文件")
    ap.add_argument("--out", default="ablation_all.json")
    args = ap.parse_args()

    kg = load_kg(args.kg)
    out: dict = {"scenarios": [], "configs": {}}

    print("=" * 80)
    print("  C 配置：仅图谱（L3 证据层失效） 与  A 配置：双驱动")
    print("=" * 80)
    rows = []
    for cid, q, gold, ctype in SCENARIOS:
        a = run_config_A(kg, q)
        c = run_config_C(kg, q)
        aa = analyze(a["answer"], gold, ctype)
        ca = analyze(c["answer"], gold, ctype)
        rows.append({
            "id": cid, "question": q, "gold_clause": gold, "case_type": ctype,
            "config_a": {**a, "analysis": aa},
            "config_c": {**c, "analysis": ca},
        })
        print(f"\n  [{cid}] {q[:58]}")
        print(f"    A 双驱动 : 引用 {aa['clauses_cited']} | 命中gold {aa['hit_gold']} "
              f"| 禁忌 {a['has_contraindications']} | 跳数 {a['chain_len']}")
        print(f"    C 仅图谱 : 引用 {ca['clauses_cited']} | 命中gold {ca['hit_gold']} "
              f"| 禁忌 {c['has_contraindications']} | 跳数 {c['chain_len']}")
    out["scenarios"] = rows

    # ---- 载入 B 配置 ----
    b_path = args.rag
    b_cases = {}
    if os.path.exists(b_path):
        bj = json.load(open(b_path, encoding="utf-8"))
        for c in bj.get("config_b_rag_only", []):
            b_cases[c["id"]] = c
    else:
        print(f"\n  ⚠️ 未找到 B 配置结果 {b_path}，对照表将缺 B 列")

    # ---- 汇总 ----
    def summarize(getter) -> dict:
        adv = [r for r in rows if r["case_type"] == "advice"]
        ref = [r for r in rows if r["case_type"] == "refusal"]
        return {
            "hit_gold_rate": round(sum(1 for r in adv if getter(r)["hit_gold"])
                                   / max(len(adv), 1), 4),
            "citation_rate": round(sum(1 for r in rows
                                       if getter(r)["has_clause_citation"])
                                   / max(len(rows), 1), 4),
            "refusal_accuracy": round(sum(1 for r in ref
                                          if getter(r)["self_declared_insufficient"])
                                      / max(len(ref), 1), 4),
            "gave_advice_when_insufficient": sum(
                1 for r in ref if getter(r)["gave_advice"]),
        }

    cfg_a = summarize(lambda r: r["config_a"]["analysis"])
    cfg_c = summarize(lambda r: r["config_c"]["analysis"])

    def bget(r):
        c = b_cases.get(r["id"])
        if not c or not c.get("ok"):
            return {"hit_gold": False, "has_clause_citation": False,
                    "self_declared_insufficient": False, "gave_advice": True}
        return c["analysis"]

    cfg_b = summarize(bget)

    out["configs"] = {"A_dual": cfg_a, "B_rag_only": cfg_b, "C_kg_only": cfg_c}

    print()
    print("=" * 80)
    print("  ★ 三配置对照表")
    print("=" * 80)
    hdr = f"  {'指标':<24}{'B 仅检索':>14}{'C 仅图谱':>14}{'A 双驱动':>14}"
    print(hdr)
    print("  " + "-" * 66)

    def row(label, key, pct=True):
        vals = []
        for cfg in (cfg_b, cfg_c, cfg_a):
            v = cfg[key]
            vals.append(f"{v*100:.1f}%" if pct else str(v))
        print(f"  {label:<24}{vals[0]:>14}{vals[1]:>14}{vals[2]:>14}")

    row("条款命中率", "hit_gold_rate")
    row("条款级引用率", "citation_rate")
    row("拒答正确率", "refusal_accuracy")
    row("信息不足仍给建议", "gave_advice_when_insufficient", pct=False)
    print("  " + "-" * 66)
    print(f"  {'禁忌提示输出':<24}{'—':>14}"
          f"{str(any(r['config_c']['has_contraindications'] for r in rows)):>14}"
          f"{str(any(r['config_a']['has_contraindications'] for r in rows)):>14}")
    print(f"  {'条文原文(caveat)':<22}{'—':>14}"
          f"{str(any(r['config_c']['has_caveat_text'] for r in rows)):>14}"
          f"{str(any(r['config_a']['has_caveat_text'] for r in rows)):>14}")
    print("=" * 80)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"  报告已保存: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
