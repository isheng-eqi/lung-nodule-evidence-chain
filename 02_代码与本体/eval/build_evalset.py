#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
肺结节处置决策 · 自测评测集生成器
================================================================

目的：解决"没有真实病例也能有金标准"的问题。

赛题要求"决策链路可溯源"，材料需要可量化指标。本项目**不使用真实患者数据**，
而是以《肺结节诊治中国专家共识（2024年版）》的 18 条推荐意见作为金标准，
系统化构造测试用例：

  · 每条推荐意见的适用区间 → 生成正例（应命中该条款）
  · 相邻条款的边界值        → 生成边界例（验证阈值判定）
  · 无关/缺失信息           → 生成拒答例（验证拒答兜底）

产出：evalset.json（可直接被 eval_runner.py 消费）

用法：
    python3 build_evalset.py --out evalset.json
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any


# ============================================================================
# 一、金标准：从共识 18 条推荐意见提取的适用区间
#
# ★ v1.2 重要变更：每条规则补上**共识原文出处**（`source_text` / `source`）。
#
# 为什么必须补：
#   独立审计指出 —— 原实现的 `GOLD_RULES` 与引擎的 `MATCH_RULES`
#   （mcp-server/kg_mcp_server.py）**是同一张表**，连 `d_max: 8`、
#   `has_risk_factor` 分支都逐字对应。因此"58/58 全通过"复现的是
#   **同义反复**（代码等于它自己），不是"系统答得对"。
#
#   修法：把金标准的**依据写进数据本身** —— 每条规则记录共识原文段落，
#   使第三方可以不看引擎代码，直接对照原文判断区间是否正确。
#
# 复核方法（第三方可自行执行）：
#   打开《肺结节诊治中国专家共识（2024年版）》全文，
#   搜索每条 `source_quote` 的原文，核对 `d_min`/`d_max`/`risk` 是否与原文一致。
# ============================================================================

GOLD_RULES: list[dict[str, Any]] = [
    # ---- 混杂性磨玻璃结节 (mGGN) ----
    {"density": "混杂性磨玻璃结节", "d_min": 0, "d_max": 8, "risk": None,
     "clause": "推荐意见14", "topic": "mGGN≤8mm 随访",
     "source": "共识 · 六（二）评估 mGGN 的细则",
     "source_quote": "孤立性mGGN直径≤8 mm者：建议在3、6、12和24个月进行CT随访",
     "boundary_note": "原文为「≤8 mm」，故 8.0 归本条、8.1 归推荐意见15"},
    {"density": "混杂性磨玻璃结节", "d_min": 8, "d_max": 30, "risk": None,
     "clause": "推荐意见15", "topic": "mGGN>8mm 处置",
     "source": "共识 · 六（二）评估 mGGN 的细则",
     "source_quote": "孤立性mGGN直径>8 mm者：建议在3个月重复胸部CT检查",
     "boundary_note": "原文为「>8 mm」；8.0 不属于本条"},
    # ---- 纯磨玻璃结节 (pGGN) ----
    {"density": "纯磨玻璃结节", "d_min": 0, "d_max": 5, "risk": None,
     "clause": "推荐意见12", "topic": "pGGN≤5mm 随访",
     "source": "共识 · 六（一）评估 pGGN 的细则",
     "source_quote": "pGGN直径≤5 mm者：建议首次6个月随访胸部CT，随后行年度胸部CT随访",
     "boundary_note": "原文为「≤5 mm」，故 5.0 归本条、5.1 归推荐意见13"},
    {"density": "纯磨玻璃结节", "d_min": 5, "d_max": 10, "risk": None,
     "clause": "推荐意见13", "topic": "pGGN 5~10mm 随访",
     "source": "共识 · 六（一）评估 pGGN 的细则",
     "source_quote": "pGGN直径5~10 mm者：建议首次3个月随访胸部CT，随后6个月行胸部CT随访",
     "boundary_note": "原文为「5~10 mm」，5.0 不属于本条"},
    # ---- 实性结节 ----
    # ⚠️ v1.2 审计发现：本条（>8mm）与下方推荐意见11（≤8mm）在 **8 mm 处重叠**。
    #    原文语义上不重叠（「>8」与「≤8」互补），但区间参数 [8,30] 与 [0,8]
    #    在采样时会在 8.0 处撞车 —— 与第 29 轮修掉的 mGGN 区间重叠同类。
    #    此处保持 `d_min: 8` 但**在采样逻辑中排除下界等于上界的情形**（见 A 类）。
    {"density": "实性肺结节", "d_min": 8, "d_max": 30, "risk": None,
     "clause": "推荐意见5", "topic": "实性结节>8mm 恶性概率评估",
     "source": "共识 · 五（三）孤立性实性结节",
     "source_quote": "孤立性不明原因结节直径>8 mm者：建议通过定性使用临床判断和（或）"
                     "定量地使用验证模型评估肺结节恶性概率",
     "boundary_note": "原文为「>8 mm」；与推荐意见11（≤8mm）互补不重叠"},
    {"density": "实性肺结节", "d_min": 0, "d_max": 8, "risk": True,
     "clause": "推荐意见11", "topic": "实性结节≤8mm 有危险因素",
     "source": "共识 · 五（二）孤立性实性结节",
     "source_quote": "存在一项或更多肺癌危险因素的直径≤8 mm的孤立性实性结节者，"
                     "建议根据结节的大小选择CT随访的频率和持续时间",
     "boundary_note": "原文为「≤8 mm」；须有危险因素"},
    {"density": "实性肺结节", "d_min": 0, "d_max": 8, "risk": False,
     "clause": "推荐意见10", "topic": "实性结节≤8mm 无危险因素",
     "source": "共识 · 五（二）孤立性实性结节",
     "source_quote": "孤立性实性结节直径≤8 mm且无肺癌危险因素者，"
                     "建议根据结节大小选择CT随访的频率与持续时间",
     "boundary_note": "原文为「≤8 mm」；须无危险因素"},
]

# 区间语义自检：确认「≤8」与「>8」互补，不在 8.0 处产生歧义归属
INTERVAL_SEMANTICS = {
    "verified": True,
    "method": ("原文用「≤8 mm」与「>8 mm」表述，语义互补；"
               "GOLD_RULES 的 [0,8] 与 [8,30] 在 8.0 处**参数重叠**，"
               "但按原文语义 8.0 唯一归属推荐意见14/11/10（含 8 的一侧）。"
               "A 类采样已排除「下界恰等于相邻规则上界」的取值，"
               "避免生成归属不唯一的用例。"),
    "complementary_pairs": [
        ("推荐意见14 (≤8)", "推荐意见15 (>8)", 8.0),
        ("推荐意见12 (≤5)", "推荐意见13 (5~10)", 5.0),
        ("推荐意见11 (≤8, 有危险因素)", "推荐意见5 (>8)", 8.0),
        ("推荐意见10 (≤8, 无危险因素)", "推荐意见5 (>8)", 8.0),
    ],
}

# 密度类型 → 中文口语表述模板（用于生成贴近真实提问的描述）
DENSITY_PHRASES = {
    "混杂性磨玻璃结节": ["混合磨玻璃结节", "混杂性磨玻璃结节", "部分实性结节", "mGGN"],
    "纯磨玻璃结节":     ["纯磨玻璃结节", "磨玻璃结节", "pGGN"],
    "实性肺结节":       ["实性结节", "实性肺结节"],
}

# 危险因素表述
RISK_PHRASES = [
    "吸烟30年",
    "吸烟指数500年支",
    "有石棉职业暴露史",
    "合并慢阻肺",
    "有肺癌家族史",
]
NO_RISK_PHRASES = ["无吸烟史", "不吸烟，无其他危险因素", "无职业暴露及家族史"]

# 患者背景模板
PATIENT_TEMPLATES = [
    "一位{age}岁{sex}，{desc}",
    "{sex}，{age}岁，{desc}",
    "患者{age}岁，{sex}性，{desc}",
]


# ============================================================================
# 一·补 临床常见测量值（D 类用例用）
#   说明：A 类在规则区间内做"覆盖抽样"，产出的是区间代表性取值（如 2.4mm、
#         14.6mm）。这类取值在数学上覆盖了区间，但临床 CT 报告中更常见的是
#         整数毫米与共识明确提及的阈值。D 类补充这批**临床常见值**用例，
#         使评测集同时具备"区间覆盖性"与"临床真实感"。
# ============================================================================

CLINICAL_DIAMETERS: dict[str, list[float]] = {
    # mGGN ≤8mm（推荐意见14）
    "mGGN_le8": [4.0, 5.0, 6.0, 8.0],
    # mGGN >8mm（推荐意见15）
    "mGGN_gt8": [9.0, 10.0, 15.0, 20.0],
    # pGGN ≤5mm（推荐意见12）
    "pGGN_le5": [3.0, 4.0, 5.0],
    # pGGN 5~10mm（推荐意见13）
    "pGGN_5to10": [6.0, 8.0, 10.0],
    # 实性结节 ≤8mm（推荐意见10 / 11）
    "solid_le8": [4.0, 6.0, 8.0],
    # 实性结节 >8mm（推荐意见5）
    "solid_gt8": [10.0, 15.0, 20.0],
}

# 各 D 类分组对应的规则与危险因素条件
D_SPECS: list[tuple[str, str, bool | None, str]] = [
    ("mGGN_le8",    "混杂性磨玻璃结节", None,  "推荐意见14"),
    ("mGGN_gt8",    "混杂性磨玻璃结节", None,  "推荐意见15"),
    ("pGGN_le5",    "纯磨玻璃结节",     None,  "推荐意见12"),
    ("pGGN_5to10",  "纯磨玻璃结节",     None,  "推荐意见13"),
    ("solid_le8",   "实性肺结节",       True,  "推荐意见11"),
    ("solid_le8",   "实性肺结节",       False, "推荐意见10"),
    ("solid_gt8",   "实性肺结节",       None,  "推荐意见5"),
]


# ============================================================================
# 二、用例生成
# ============================================================================

def _make_desc(density_phrase: str, diameter: float,
               risk_phrase: str, solid: float | None) -> str:
    parts = [f"{diameter:g}mm{density_phrase}"]
    if solid is not None:
        parts.append(f"实性成分{solid:g}mm")
    parts.append(risk_phrase)
    return "，".join(parts)


def build_evalset() -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    cid = 0

    # ---------------- A 类：正例（每条推荐意见的典型适用区间）----------------
    # ⚠️ 区间边界必须与 B 类边界用例的期望**保持一致**：
    #    mGGN 8.0mm → 推荐意见14（≤8 侧）；8.1mm → 推荐意见15
    #    pGGN 5.0mm → 推荐意见12（≤5 侧）；5.1mm → 推荐意见13
    #    实性 8.0mm → 推荐意见11（≤8 侧）；8.1mm → 推荐意见5
    #
    # v1.2 修正：原区间写成 (0,8] 与 [8,30] 在 8mm 处**重叠**，
    #           导致 A 类抽样取到 8.0mm 时归属不唯一
    #           （评测报出 A005/A006 期望与引擎判定不符，实为用例区间定义错误）。
    #           现改为半开区间 (lo, hi]，即下界不含、上界含。
    for rule in GOLD_RULES:
        density = rule["density"]
        phrases = DENSITY_PHRASES[density]
        lo, hi = rule["d_min"], rule["d_max"]

        # v1.2 修正：改用**临床合理的整数毫米**取值。
        #
        # 原实现按区间比例取点（lo + span×0.3 / ×0.7），产出 2.4 / 5.6 / 14.6 /
        # 23.4 mm 这类数值 —— 数学上覆盖了区间，但**临床上不自然**：
        # 例如「2.4mm 混杂性磨玻璃结节，实性成分 0.7mm」在真实报告中极少出现
        # （如此小的病灶通常不会被描述为混合磨玻璃结节）。
        #
        # 现在按密度类型取 CT 报告中常见的实测值；F 类仍保留一批
        # 临床常见值用例，两类合起来既覆盖区间又贴近真实。
        PREFERRED = {
            "混杂性磨玻璃结节": [5.0, 8.0],    # mGGN 常见报告值
            "纯磨玻璃结节":     [3.0, 9.0],    # pGGN 常见报告值
            "实性肺结节":       [10.0, 20.0],  # 实性结节常见报告值
        }
        diams = [d for d in PREFERRED.get(density, []) if lo <= d <= hi]
        if not diams:
            # 兜底：取区间中点附近的整数值
            mid = (lo + hi) / 2
            diams = [round(mid)]

        # ---- 半开区间校正：避免落在相邻规则的边界上被两边同时覆盖 ----
        # 若某取值恰等于本区间的下界，且存在另一条同密度规则以其为上界，
        # 则该值应归属**上界包含它**的那条规则，本规则不再采样它。
        _same = [r for r in GOLD_RULES if r["density"] == density and r is not rule]
        diams = [
            d for d in diams
            if not (d == lo and any(r["d_max"] == d for r in _same))
        ]
        if not diams:
            mid = (lo + hi) / 2
            diams = [round(mid)]

        for d in diams:
            for i, ph in enumerate(phrases[:2]):
                risk_needed = rule["risk"]
                if risk_needed is True:
                    rp = RISK_PHRASES[cid % len(RISK_PHRASES)]
                elif risk_needed is False:
                    rp = NO_RISK_PHRASES[cid % len(NO_RISK_PHRASES)]
                else:
                    rp = RISK_PHRASES[cid % len(RISK_PHRASES)] if cid % 2 == 0 \
                        else NO_RISK_PHRASES[cid % len(NO_RISK_PHRASES)]
                # mGGN 补充实性成分
                solid = None
                if density == "混杂性磨玻璃结节":
                    solid = round(min(d * 0.3, 8), 1)
                desc = _make_desc(ph, d, rp, solid)
                tmpl = PATIENT_TEMPLATES[cid % len(PATIENT_TEMPLATES)]
                age = 45 + (cid * 3) % 30
                sex = "男性" if cid % 2 == 0 else "女性"
                q = tmpl.format(age=age, sex=sex, desc=desc) + "，该怎么处理？"
                cid += 1
                cases.append({
                    "id": f"A{cid:03d}",
                    "type": "positive",
                    "question": q,
                    "expected_clause": rule["clause"],
                    "expected_topic": rule["topic"],
                    # ★ v1.2：把金标准的**原文出处**写进用例，
                    # 使第三方可不看引擎代码、直接对照共识原文核对期望值
                    "gold_source": rule.get("source", ""),
                    "gold_quote": rule.get("source_quote", ""),
                    "gold_boundary_note": rule.get("boundary_note", ""),
                    "facts": {"density": density, "diameter_mm": d,
                              "has_risk_factor": bool(risk_needed) if risk_needed is not None else None},
                    "note": "正例：应命中指定条款",
                })

    # ---------------- B 类：边界例（阈值附近，验证判定）----------------
    boundary_specs = [
        ("混杂性磨玻璃结节", 7.9, "推荐意见14", "mGGN 接近 8mm 下边界"),
        ("混杂性磨玻璃结节", 8.1, "推荐意见15", "mGGN 刚过 8mm 阈值"),
        ("混杂性磨玻璃结节", 8.0, "推荐意见14", "mGGN 恰在 8mm 阈值（取≤侧）"),
        ("纯磨玻璃结节", 5.0, "推荐意见12", "pGGN 恰在 5mm 阈值（取≤侧）"),
        ("纯磨玻璃结节", 5.1, "推荐意见13", "pGGN 刚过 5mm 阈值"),
        ("实性肺结节", 8.0, "推荐意见11", "实性结节恰在 8mm（≤8 分支）"),
        ("实性肺结节", 8.1, "推荐意见5", "实性结节刚过 8mm"),
        ("实性肺结节", 4.0, "推荐意见11", "实性小结节恰在 4mm 分界"),
    ]
    for density, d, clause, note in boundary_specs:
        ph = DENSITY_PHRASES[density][0]
        risk = "吸烟30年" if "推荐意见11" in clause else "无吸烟史"
        solid = round(min(d * 0.25, 8), 1) if density == "混杂性磨玻璃结节" else None
        desc = _make_desc(ph, d, risk, solid)
        cid += 1
        cases.append({
            "id": f"B{cid:03d}",
            "type": "boundary",
            "question": f"患者58岁，男性，{desc}，请问随访方案？",
            "expected_clause": clause,
            "expected_topic": note,
            "facts": {"density": density, "diameter_mm": d},
            "note": "边界例：验证阈值判定",
        })

    # ---------------- C 类：拒答例（信息不足，验证兜底）----------------
    refuse_cases = [
        "我有肺结节，该怎么办？",
        "体检发现肺部有个阴影，需要处理吗？",
        "报告上写着肺结节，严重吗？",
        "医生说我肺上有个小结节，要手术吗？",
    ]
    for q in refuse_cases:
        cid += 1
        cases.append({
            "id": f"C{cid:03d}",
            "type": "refusal",
            "question": q,
            "expected_clause": None,
            "expected_topic": "拒答或追问缺失信息",
            "facts": {},
            "note": "拒答例：缺少结节直径，应追问而非给建议",
        })

    # ---------------- D 类：禁忌与边界判定例 ----------------
    # 判据为"禁忌提示是否出现"，而非主条款编号（引擎会先输出处置条款）
    contra_cases = [
        ("一位55岁男性，8mm混合磨玻璃结节，实性成分2mm，吸烟30年",
         "推荐意见14", "PET-CT 不适用于实性成分≤8mm 的混杂性病灶", "PET-CT"),
        ("女，50岁，9mm混杂性磨玻璃结节，实性成分3mm",
         "推荐意见15", "PET-CT 不适用判定", "PET-CT"),
    ]
    for desc, clause, note, kw in contra_cases:
        cid += 1
        cases.append({
            "id": f"D{cid:03d}",
            "type": "contraindication",
            "question": desc + "，能否做 PET-CT 评估？",
            "expected_clause": clause,
            "expected_topic": note,
            "expected_keyword": kw,
            "facts": {},
            "note": "禁忌例：验证 contraindications 是否给出 PET-CT 不适用提示",
        })

    # ---------------- E 类：分级诊疗归属例 ----------------
    # 判据为 referral 字段是否指向正确的机构层级
    # 注意：需明确密度类型，否则「微小结节」既可能被理解为尺寸分类，
    # 也可能被引擎按实性结节分支处理（共识的 10/11 条即针对实性结节），
    # 造成用例歧义。此处统一写为"实性结节"以消除歧义。
    referral_cases = [
        ("患者60岁，4mm实性结节，无危险因素", "基层医院随访管理"),
        ("患者52岁，7mm实性结节，吸烟20年", "转肺结节诊治分中心管理"),
        ("患者65岁，15mm混杂性磨玻璃结节，吸烟40年", "肺癌防治联盟"),
    ]
    for desc, expected in referral_cases:
        cid += 1
        cases.append({
            "id": f"E{cid:03d}",
            "type": "referral",
            "question": desc + "，应该在什么级别的医院管理？",
            "expected_clause": "推荐意见18",
            "expected_topic": expected,
            "facts": {},
            "note": "分级诊疗例：验证 referral 字段的机构归属",
        })

    # ---------------- F 类：临床常见测量值例 ----------------
    # 与 A 类的区别：A 类在区间内做数学覆盖抽样；F 类使用 CT 报告中
    # 实际常见的整数毫米与共识明确提及的阈值，验证"间距抽样"之外的
    # 临床真实取值同样可被正确判定。
    for key, density, risk_flag, clause in D_SPECS:
        for d in CLINICAL_DIAMETERS[key]:
            ph = DENSITY_PHRASES[density][0]
            if risk_flag is True:
                rp = RISK_PHRASES[cid % len(RISK_PHRASES)]
            elif risk_flag is False:
                rp = NO_RISK_PHRASES[cid % len(NO_RISK_PHRASES)]
            else:
                rp = RISK_PHRASES[cid % len(RISK_PHRASES)]
            solid = round(min(d * 0.3, 6), 1) if density == "混杂性磨玻璃结节" else None
            desc = _make_desc(ph, d, rp, solid)
            age = 48 + (cid * 5) % 25
            sex = "男性" if cid % 2 == 0 else "女性"
            tmpl = PATIENT_TEMPLATES[cid % len(PATIENT_TEMPLATES)]
            q = tmpl.format(age=age, sex=sex, desc=desc) + "，应该如何处理？"
            cid += 1
            cases.append({
                "id": f"F{cid:03d}",
                "type": "positive",
                "question": q,
                "expected_clause": clause,
                "expected_topic": f"临床常见值 {d:g}mm",
                "facts": {"density": density, "diameter_mm": d,
                          "has_risk_factor": risk_flag},
                "note": "临床常见值例：使用 CT 报告常见整数毫米，验证判定一致性",
            })

    stats = {
        "total": len(cases),
        "positive": sum(1 for c in cases if c["type"] == "positive"),
        "boundary": sum(1 for c in cases if c["type"] == "boundary"),
        "refusal": sum(1 for c in cases if c["type"] == "refusal"),
        "contraindication": sum(1 for c in cases if c["type"] == "contraindication"),
        "referral": sum(1 for c in cases if c["type"] == "referral"),
        "clinical_value": sum(1 for c in cases
                              if c["note"].startswith("临床常见值")),
        "clauses_covered": sorted({c["expected_clause"] for c in cases
                                   if c["expected_clause"]}),
    }
    return {
        "name": "肺结节处置决策自测评测集",
        "version": "1.1",
        "gold_standard": "《肺结节诊治中国专家共识（2024年版）》18条推荐意见",
        "data_source_note": (
            "本评测集不使用真实患者数据。所有用例由共识条款的适用区间系统化生成，"
            "金标准为条款编号本身，可机器判定。"
        ),
        "case_types_note": {
            "A": "正例——在规则区间内做覆盖抽样（区间代表性取值）",
            "B": "边界例——阈值附近取值，验证 ≤ / > 判定",
            "C": "拒答例——信息不足，应追问而非给建议",
            "D": "禁忌例——验证 contraindications 字段",
            "E": "分级诊疗例——验证 referral 字段",
            "F": "临床常见值例——CT 报告中常见的整数毫米与共识阈值",
        },
        "stats": stats,
        "cases": cases,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="生成肺结节处置决策评测集")
    ap.add_argument("--out", default="evalset.json")
    args = ap.parse_args()

    ds = build_evalset()
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(ds, f, ensure_ascii=False, indent=2)

    s = ds["stats"]
    print("=" * 62)
    print("  评测集已生成")
    print("=" * 62)
    print(f"  总用例        : {s['total']}")
    print(f"  正例          : {s['positive']}")
    print(f"  边界例        : {s['boundary']}")
    print(f"  拒答例        : {s['refusal']}")
    print(f"  禁忌例        : {s['contraindication']}")
    print(f"  分级诊疗例    : {s['referral']}")
    print(f"  覆盖条款      : {len(s['clauses_covered'])} 条 "
          f"{','.join(s['clauses_covered'])}")
    print(f"  输出          : {args.out}")
    print("=" * 62)
    return 0


if __name__ == "__main__":
    sys.exit(main())
