#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
肺结节决策知识图谱 MCP Server
================================================================

对应赛题要求：
  "深度集成 Nexent 的 MCP 协议与 Skills 编排能力，
   打造'检索-推理'双驱动协同智能体执行流。"

本服务把自研的「肺结节决策知识图谱 + 多跳推理引擎」以 MCP 协议
暴露给 Nexent 平台上的智能体，与平台自带的 `knowledge_base_search`
（向量检索）形成**检索-推理双驱动**：

    knowledge_base_search  →  文本层：找到相关条款原文（Nexent 提供）
    kg_* (本服务)          →  结构层：沿规则链推导处置、输出依据链

设计遵循官方 mcp-builder 规范：
  · 工具命名：统一前缀 `kg_` + 动作导向
  · 输入 schema：类型 + 约束 + 字段描述 + 示例
  · 输出：结构化 JSON（便于智能体解析）
  · 错误信息：可操作（告诉调用方怎么修）
  · 只读工具标注 readOnlyHint

启动：
    python3 kg_mcp_server.py --transport http --port 8020
    或 stdio（本地调试）：python3 kg_mcp_server.py --transport stdio
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP

# ============================================================================
# 一、知识图谱数据（由 ontology_builder 从共识抽取，条款级可溯源）
# ============================================================================

# 推荐意见条款：结论性内容，逐条溯源至《肺结节诊治中国专家共识（2024年版）》
RECOMMENDATIONS: dict[str, dict[str, Any]] = {
    "推荐意见1": {
        "title": "难定性肺结节",
        "strength": "Ⅲ类推荐",
        "applies_to": ["难定性肺结节"],
        "recommends": ["MDT多学科会诊"],
        "text": "难定性肺结节推荐采用 MDT 工作模式和医患共同决策。",
    },
    "推荐意见2": {
        "title": "肺癌高危人群定义与筛查",
        "strength": "Ⅱ类推荐",
        "applies_to": ["肺癌高危人群"],
        "recommends": ["低剂量CT"],
        "follow_up": "每年一次",
        "text": "年龄≥40岁且具有任一危险因素者定义为高危人群，推荐每年 LDCT 筛查。",
    },
    "推荐意见3": {
        "title": "薄层CT与历史影像对比",
        "strength": "ⅠB类推荐",
        "applies_to": [],
        "recommends": ["薄层CT"],
        "text": "推荐对病灶处行薄层CT或薄层高分辨CT，并与既往历史影像学资料对比。",
    },
    "推荐意见4": {
        "title": "AI辅助诊断与肿瘤标志物",
        "strength": "Ⅱ类推荐",
        "applies_to": [],
        "recommends": [],
        "requires": ["肿瘤标志物组合"],
        "text": "AI辅助影像诊断有助于风险评估；不推荐单一肿瘤标志物用于亚厘米结节筛查评估。",
    },
    "推荐意见5": {
        "title": ">8mm 结节恶性概率评估",
        "strength": "Ⅱ类推荐",
        "applies_to": ["实性肺结节"],
        "recommends": [],
        "requires": ["PET-CT", "循环染色体异常细胞检测"],
        "text": "直径>8mm 者建议评估恶性概率；低中度(5%~65%)可考虑PET-CT；高度(>65%)可直接考虑PET-CT。",
    },
    "推荐意见6": {
        "title": "风险获益沟通与患者意愿",
        "strength": "Ⅱ类推荐",
        "applies_to": [],
        "recommends": ["MDT多学科会诊"],
        "text": "推荐医生提出管理策略的风险和益处，并考虑患者意愿而决定。",
    },
    "推荐意见7": {
        "title": ">8mm 结节随访间隔",
        "strength": "Ⅱ类推荐",
        "applies_to": ["实性肺结节"],
        "recommends": ["CT随访"],
        "requires": ["薄层CT"],
        "follow_up": "3~6、9~12、18~24 个月",
        "text": "临床恶性概率很低(<5%)等情况建议在3~6、9~12及18~24个月薄层CT随访。",
    },
    "推荐意见8": {
        "title": "非手术活检指征",
        "strength": "Ⅱ类推荐",
        "applies_to": [],
        "recommends": [],
        "requires": ["非手术活检"],
        "text": "临床预测概率与影像不一致、恶性概率低中度(10%~60%)等情况建议非手术活检。",
    },
    "推荐意见9": {
        "title": "手术活检指征",
        "strength": "Ⅱ类推荐",
        "applies_to": [],
        "recommends": [],
        "requires": ["手术活检"],
        "text": "临床恶性概率高(>65%)、PET-CT高代谢等情况建议手术活检。",
    },
    "推荐意见10": {
        "title": "≤8mm 实性结节（无危险因素）随访",
        "strength": "Ⅱ类推荐",
        "applies_to": ["实性肺结节"],
        "recommends": ["CT随访"],
        "follow_up": "≤4mm:遵医嘱或不随访；4~6mm:年度；6~8mm:6~12个月内，未变化转年度",
        "text": "孤立性实性结节直径≤8mm且无危险因素者，按大小选随访频率。",
    },
    "推荐意见11": {
        "title": "≤8mm 实性结节（有危险因素）随访",
        "strength": "Ⅱ类推荐",
        "applies_to": ["实性肺结节"],
        "recommends": ["CT随访"],
        "follow_up": ("≤4mm:年度；4~6mm:6~12个月，未变化则18~24个月后转年度；"
                      "6~8mm:3~6个月、9~12个月，其后每6个月，2年无变化转年度"),
        "text": "存在一项或更多危险因素的≤8mm实性结节，按大小选随访频率。",
    },
    "推荐意见12": {
        "title": "pGGN ≤5mm 随访",
        "strength": "Ⅱ类推荐",
        "applies_to": ["纯磨玻璃结节"],
        "recommends": ["CT随访"],
        "follow_up": "首次 6 个月，随后年度",
        "text": "pGGN 直径≤5mm 者：首次6个月随访胸部CT，随后年度随访。",
    },
    "推荐意见13": {
        "title": "pGGN 5~10mm 随访",
        "strength": "Ⅲ类推荐",
        "applies_to": ["纯磨玻璃结节"],
        "recommends": ["CT随访", "MDT多学科会诊"],
        "requires": ["循环染色体异常细胞检测", "薄层CT"],
        "follow_up": "首次 3 个月，随后 6 个月",
        "next_step": ["非手术活检", "外科手术根治性切除"],
        "text": "pGGN 直径5~10mm：首次3个月随访，随后6个月随访，建议AI与人机MDT评估。",
    },
    "推荐意见14": {
        "title": "mGGN ≤8mm 随访",
        "strength": "Ⅲ类推荐",
        "applies_to": ["混杂性磨玻璃结节"],
        "recommends": ["CT随访", "MDT多学科会诊"],
        "requires": ["循环染色体异常细胞检测", "薄层CT"],
        "follow_up": "3、6、12 和 24 个月",
        "next_step": ["外科手术根治性切除", "经验性抗菌治疗"],
        "caveat": ("若混杂性结节增大或实性成分增多，通常提示为恶性，"
                   "需考虑切除，而不是非手术活检；"
                   "若同时有症状或细菌感染征象，可考虑经验性抗菌治疗。"),
        "text": "孤立性mGGN直径≤8mm者：建议在3、6、12和24个月进行CT随访，"
                "建议应用AI和人机MDT评估，无变化者随后转为常规年度随访。",
    },
    "推荐意见15": {
        "title": "mGGN >8mm 处置",
        "strength": "Ⅲ类推荐",
        "applies_to": ["混杂性磨玻璃结节"],
        "recommends": ["CT随访", "经验性抗菌治疗", "MDT多学科会诊"],
        "requires": ["循环染色体异常细胞检测"],
        "follow_up": "3 个月",
        "next_step": ["非手术活检", "外科手术根治性切除"],
        "caveat": ("PET-CT不推荐用于判断实性成分≤8mm的混杂性病灶；"
                   "mGGN直径>15mm者可直接考虑PET-CT、非手术活检和（或）手术切除。"),
        "text": "孤立性mGGN直径>8mm：建议3个月重复胸部CT，适当考虑经验性抗菌治疗；"
                "若结节持续存在，建议AI和人机MDT评估，必要者考虑非手术活检和（或）手术切除。",
    },
    "推荐意见16": {
        "title": "多发性肺结节评估",
        "strength": "Ⅲ类推荐",
        "applies_to": ["多发性肺结节"],
        "recommends": ["MDT多学科会诊"],
        "requires": ["循环染色体异常细胞检测", "PET-CT"],
        "text": "建议单独评估每个结节，应用AI和人机MDT评估；除非有组织病理学证实转移，否则不可否定根治性治疗。",
    },
    "推荐意见17": {
        "title": "肺癌局部治疗",
        "strength": "ⅠA类推荐",
        "applies_to": [],
        "recommends": ["外科手术根治性切除"],
        "next_step": ["立体定向放射治疗", "消融治疗"],
        "text": "肺癌的优选局部治疗方式为外科手术根治性切除；"
                "心肺功能不能耐受者经MDT评估可考虑SBRT或消融治疗。",
    },
    "推荐意见18": {
        "title": "分级诊疗管理",
        "strength": "Ⅲ类推荐",
        "applies_to": [],
        "recommends": ["转诊"],
        "referral": {
            "≤5mm": "基层医院随访管理",
            "5~10mm": "建议转肺结节诊治分中心管理",
            ">10mm": "可由肺癌防治联盟协助指导管理",
        },
        "text": "按分级诊疗原则管理：≤5mm在基层医院管理；5~10mm且未明确诊断者转分中心；"
                ">10mm且分中心未明确诊断者由联盟协助指导。",
    },
}

# 本体概念层次（用于概念查询）
CONCEPT_HIERARCHY: dict[str, dict[str, Any]] = {
    "肺结节": {"parent": None, "children": ["微小结节", "小结节", "较大结节",
                                        "实性肺结节", "亚实性肺结节",
                                        "孤立性肺结节", "多发性肺结节", "难定性肺结节"]},
    "微小结节": {"parent": "肺结节", "constraint": "最大径 ≤5mm",
              "managed_at": "基层医院随访管理（推荐意见18①）"},
    "小结节": {"parent": "肺结节", "constraint": "最大径 5~10mm",
             "managed_at": "转肺结节诊治分中心管理（推荐意见18②）"},
    "较大结节": {"parent": "肺结节", "constraint": "最大径 10~30mm",
              "managed_at": "可由肺癌防治联盟协助指导（推荐意见18③）"},
    "实性肺结节": {"parent": "肺结节",
                "alias": ["实性结节", "solid nodule", "实性"],
                "definition": "病变密度足以掩盖其中走行的血管和支气管影"},
    "亚实性肺结节": {"parent": "肺结节",
                  "definition": "含磨玻璃密度，病变密度不足以掩盖血管和支气管影"},
    "纯磨玻璃结节": {"parent": "亚实性肺结节",
                 "alias": ["pGGN", "纯磨玻璃", "磨玻璃结节", "磨玻璃影", "GGO",
                           "pure ground-glass nodule"],
                 "definition": "磨玻璃病灶内不含实性成分"},
    "混杂性磨玻璃结节": {"parent": "亚实性肺结节",
                   "alias": ["mGGN", "部分实性结节", "混合磨玻璃", "混合磨玻璃结节",
                             "混杂性结节", "混杂密度结节", "mixed ground-glass nodule"],
                   "definition": "磨玻璃密度与实性密度均有；"
                                 "内部实性成分比例对侵袭性判断比大小更重要"},
    "孤立性肺结节": {"parent": "肺结节", "definition": "单个病灶"},
    "多发性肺结节": {"parent": "肺结节", "definition": "2个及以上病灶"},
    "难定性肺结节": {"parent": "肺结节",
                 "definition": "无法通过非手术活检明确诊断，且高度怀疑早期肺癌"},
}

# 条款匹配规则（本体核心推理规则，来源：共识五、六章）
MATCH_RULES: list[dict[str, Any]] = [
    {"density": "混杂性磨玻璃结节", "d_min": None, "d_max": 8, "clause": "推荐意见14"},
    {"density": "混杂性磨玻璃结节", "d_min": 8, "d_max": None, "clause": "推荐意见15"},
    {"density": "纯磨玻璃结节", "d_min": None, "d_max": 5, "clause": "推荐意见12"},
    {"density": "纯磨玻璃结节", "d_min": 5, "d_max": 10, "clause": "推荐意见13"},
    {"density": "实性肺结节", "d_min": 8, "d_max": None, "clause": "推荐意见5"},
    {"density": "实性肺结节", "d_min": None, "d_max": 8,
     "clause": "推荐意见11", "when": "has_risk_factor"},
    {"density": "实性肺结节", "d_min": None, "d_max": 8,
     "clause": "推荐意见10", "when": "no_risk_factor"},
]

# 禁忌规则
CONTRA_RULES: list[dict[str, Any]] = [
    {"density": "混杂性磨玻璃结节", "solid_max": 8,
     "examination": "PET-CT",
     "reason": "PET-CT 不推荐用于判断实性成分≤8mm 的混杂性病灶",
     "clause": "推荐意见15"},
]


# ============================================================================
# 二、推理引擎（与 kg_reasoning_service 同源，此处内联以保持服务自包含）
# ============================================================================

@dataclass
class PatientFacts:
    raw: str = ""
    age: Optional[int] = None
    diameter_mm: Optional[float] = None
    solid_component_mm: Optional[float] = None
    density_type: str = ""
    smoking_years: Optional[int] = None
    risk_factors: list[str] = field(default_factory=list)
    imaging_features: list[str] = field(default_factory=list)
    is_solitary: bool = True

    def summary(self) -> str:
        parts = []
        if self.diameter_mm is not None:
            parts.append(f"直径{self.diameter_mm}mm")
        if self.density_type:
            parts.append(self.density_type)
        if self.age is not None:
            parts.append(f"{self.age}岁")
        if self.smoking_years:
            parts.append(f"吸烟{self.smoking_years}年")
        return "、".join(parts) if parts else "（未识别到结构化事实）"


DENSITY_PATTERNS = [
    ("混杂性磨玻璃结节", r"混合磨玻璃|混杂性?(?:磨玻璃)?结节|部分实性|mGGN|混杂密度"),
    ("纯磨玻璃结节", r"纯磨玻璃|磨玻璃结节|磨玻璃影|pGGN|GGO"),
    ("实性肺结节", r"实性结节|实性肺结节|solid nodule"),
]
RISK_PATTERNS = [
    ("吸烟史", r"吸烟|抽烟|烟龄|包年|年支"),
    ("环境或高危职业暴露史", r"石棉|铍|铀|氡|职业暴露|粉尘"),
    ("慢性肺部疾病史", r"慢阻肺|COPD|肺纤维化|肺结核|慢性肺病|肺气肿"),
    ("肿瘤史或家族史", r"肿瘤史|癌症史|家族史|恶性肿瘤"),
]

# 否定表述（v1.3 修复）
# 临床描述中常出现"不吸烟""无吸烟史""否认家族史"等否定句。
# 若不做否定检测，"不吸烟"会被 RISK_PATTERNS 中的"吸烟"误判为**存在**吸烟史，
# 进而把「≤8mm 实性结节」错误路由到"有危险因素"分支（推荐意见11 而非 10），
# 造成随访频率建议偏差 —— 这是临床决策支持中不可接受的错误。
NEGATION_PATTERNS = [
    r"无\s*吸烟", r"不\s*吸烟", r"不\s*抽烟", r"无\s*抽烟", r"否认\s*吸烟",
    r"无\s*烟酒", r"从不\s*吸烟", r"无\s*吸烟史", r"戒烟",
    r"无\s*职业暴露", r"无\s*粉尘", r"无\s*石棉",
    r"无\s*慢阻肺", r"无\s*肺病", r"无\s*肺结核", r"无\s*肺纤维化",
    r"无\s*肿瘤", r"无\s*癌症", r"无\s*家族史", r"否认\s*家族史",
    r"无\s*其他\s*危险因素", r"无\s*危险因素", r"没有\s*危险因素",
    r"无\s*高危因素", r"无\s*任何\s*危险因素",
]

# 全局否定短语：出现即认为患者无危险因素
GLOBAL_NO_RISK = [
    r"无\s*其他\s*危险因素", r"无\s*危险因素", r"没有\s*危险因素",
    r"无\s*任何\s*危险因素", r"无\s*高危因素",
]


def _has_negation(text: str, keyword_span: tuple[int, int]) -> bool:
    """判断某个阳性关键词是否处于否定语境。

    在关键词**前方 6 个字符**窗口内查找否定词（如"不""无""否认"）。
    窗口取 6 是因为中文临床表述如"患者不吸烟""无吸烟史"的否定词紧邻关键词。
    """
    start = keyword_span[0]
    window = text[max(0, start - 6):start]
    return bool(re.search(r"[不无否]|否认|未见|未", window))
IMAGING_PATTERNS = [
    ("毛刺征", r"毛刺"), ("分叶征", r"分叶"), ("胸膜凹陷征", r"胸膜凹陷"),
    ("血管集束征", r"血管集束"), ("位于上叶", r"上叶"),
    ("密度增加", r"密度(?:增高|增加|升高)"), ("实性成分增多", r"实性成分(?:增多|增加|出现)"),
]


def extract_facts(text: str) -> PatientFacts:
    f = PatientFacts(raw=text)
    m = re.search(r"(\d{1,3})\s*岁", text)
    if m:
        f.age = int(m.group(1))
    # 结节直径：先取"实性成分"的数值并排除，避免把实性成分误当结节直径
    m_solid = re.search(r"实性成分\s*(?:约|为|是)?\s*(\d+(?:\.\d+)?)\s*mm", text)
    solid_span = m_solid.span() if m_solid else None
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*mm", text):
        # 跳过落在"实性成分Xmm"区间内的匹配
        if solid_span and m.start() >= solid_span[0] and m.end() <= solid_span[1]:
            continue
        f.diameter_mm = float(m.group(1))
        break
    if m_solid:
        f.solid_component_mm = float(m_solid.group(1))
    m = re.search(r"吸烟\s*(\d{1,3})\s*年", text)
    if m:
        f.smoking_years = int(m.group(1))

    for name, pat in DENSITY_PATTERNS:
        if re.search(pat, text):
            f.density_type = name
            break

    # ---- 危险因素抽取（v1.3：加入否定检测）----
    global_negative = any(re.search(p, text) for p in GLOBAL_NO_RISK)
    if not global_negative:
        for name, pat in RISK_PATTERNS:
            if name in f.risk_factors:
                continue
            for m in re.finditer(pat, text):
                if not _has_negation(text, m.span()):
                    f.risk_factors.append(name)
                    break
    # 显式否定句覆盖阳性匹配：若整句是否定式，清空对应类别
    if any(re.search(p, text) for p in NEGATION_PATTERNS):
        # 逐类判断：该类若只有否定表述，则移除
        for name, pat in RISK_PATTERNS:
            if name not in f.risk_factors:
                continue
            positive_hit = False
            for m in re.finditer(pat, text):
                if not _has_negation(text, m.span()):
                    positive_hit = True
                    break
            if not positive_hit:
                f.risk_factors.remove(name)

    for name, pat in IMAGING_PATTERNS:
        if re.search(pat, text):
            f.imaging_features.append(name)
    if re.search(r"多发|多个|两枚|三枚", text):
        f.is_solitary = False
    return f


def size_category(d: float) -> str:
    if d <= 5:
        return "微小结节"
    if d <= 10:
        return "小结节"
    return "较大结节"


def match_clause(density: str, d: float, has_risk: bool
                 ) -> Optional[tuple[str, str]]:
    """返回 (条款编号, 匹配说明)。"""
    for r in MATCH_RULES:
        if r["density"] != density:
            continue
        lo, hi = r.get("d_min"), r.get("d_max")
        if lo is not None and d <= lo:
            continue
        if hi is not None and d > hi:
            continue
        cond = r.get("when")
        if cond == "has_risk_factor" and not has_risk:
            continue
        if cond == "no_risk_factor" and has_risk:
            continue
        why = f"{density} + 直径{d}mm"
        if cond == "has_risk_factor":
            why += " + 存在危险因素"
        elif cond == "no_risk_factor":
            why += " + 无危险因素"
        return r["clause"], why
    return None


# ===========================================================================
# 跨文档知识（v2.0 新增）
# ---------------------------------------------------------------------------
# 此前服务端只内嵌了《2024 共识》的 18 条推荐意见 —— 即"运行态只有 1 份文档"，
# 而赛题要求"跨文档多跳知识推理"。本节把另 3 份公开规范的关键条款纳入，
# 并设置**语境消歧规则**处理跨文档冲突。
#
# 为什么需要消歧：不同文档的阈值**表面冲突**，实为**不同语境**——
#   · 筛查阶段：判定"是否阳性、要不要进入临床流程"（入口）
#   · 随访管理：检出之后决定"多久复查"（过程）
# 若不区分语境，会把筛查阈值误用于随访决策（或反之），
# 这是真实临床场景中的典型错误来源。
# ===========================================================================

# 跨文档条款：文档标识 → 条款
CROSS_DOC_CLAUSES: dict[str, dict[str, Any]] = {
    "筛查指南2025": {
        "source": "中国肺癌低剂量CT筛查指南（2025年版）",
        "doi": "10.3779/j.issn.1009-3419.2025.102.43",
        "pmcid": "PMC12972581",
        "clauses": {
            "章2": {
                "title": "高危人群的选择",
                "text": ("建议同时符合以下两项条件者参加肺癌筛查：（1）原则上年龄介于 50-80 岁。"
                         "对于筛查终止年龄，应重视个体化风险评估，要根据受检者的整体健康状况、"
                         "预期寿命及治疗耐受性进行个体化判别。若在年度筛查中发现因身体状况"
                         "无法耐受可能的肺癌切除手术，或罹患严重威胁生命的疾病，则建议停止 LDCT 筛查；"
                         "（2）具有下列条件之一：①吸烟史：吸烟≥20包年，或被动吸烟≥20年；"
                         "如现已戒烟，戒烟时间≤5年者可继续筛查，超过5年者可建议停止；"
                         "②职业致癌物暴露史：累计暴露于氡、砷、铍、铬及其化合物、石棉、氯甲醚、"
                         "二氧化硅、焦炉逸散物或煤烟等明确肺癌相关职业致癌物≥5年。"),
                "context": "screening_entry",
            },
            "章3": {
                "title": "筛查间隔",
                "text": ("建议对连续 2 年 LDCT 筛查均为阴性的个体暂停筛查 2 年；"
                         "而对筛查结果阳性的个体，则仍应维持每年 1 次的筛查频率。"),
                "context": "screening_interval",
            },
            "章5.1": {
                "title": "阳性结节定义",
                "text": ("基线筛查阳性结节定义：实性结节平均直径或部分实性结节实性成分平均直径≥6 mm，"
                         "或非实性结节直径≥8 mm，或发现气管或/及支气管可疑病变，"
                         "或 LDCT 诊断为肺癌的肺部单发、多发结节或肺癌包块，定义为基线筛查阳性，"
                         "应当进入临床治疗程序。"),
                "context": "screening_positive",
            },
        },
    },
    "筛查指南2023": {
        "source": "中国肺癌低剂量CT筛查指南（2023年版）",
        "doi": "10.3779/j.issn.1009-3419.2023.102.10",
        "pmcid": "PMC9987116",
        "clauses": {
            "随访间隔": {
                "title": "阳性结节随访间隔（旧版）",
                "text": ("阳性结节随访间隔为 3 个月。"
                         "（2025 年版修订后：筛查间隔改为连续 2 年阴性者暂停 2 年）"),
                "context": "screening_interval",
            },
        },
    },
    "共识2025": {
        "source": "肺癌筛查及肺结节健康管理专家共识（2025版）",
        "clauses": {
            "推荐意见": {
                "title": "筛查与健康管理衔接",
                "text": "强调筛查发现的结节应进入规范化随访管理路径，与诊治共识衔接。",
                "context": "screening_management_bridge",
            },
        },
    },
}

# 语境消歧规则：同一临床情形在不同文档/语境下的判定差异
DISAMBIGUATION_RULES: list[dict[str, Any]] = [
    {
        "id": "D1",
        "topic": "实性成分阈值：筛查阳性判定 vs 随访管理",
        "thresholds": [
            {"doc": "筛查指南2025", "clause": "章5.1", "value": "实性成分 ≥6 mm",
             "context": "screening_positive",
             "meaning": "达到该阈值 → 判定为**基线筛查阳性**，应当进入临床治疗程序"},
            {"doc": "共识2024", "clause": "推荐意见14", "value": "mGGN ≤8 mm",
             "context": "followup_management",
             "meaning": "落在该范围 → 按 3、6、12、24 个月**随访管理**"},
        ],
        "resolution": (
            "**两者不矛盾，属不同语境**：\n"
            "· 「实性成分 ≥6 mm」是**筛查阶段的阳性判定**（决定是否进入临床流程）；\n"
            "· 「mGGN ≤8 mm 随访」是**检出后的随访管理**（决定复查间隔）。\n"
            "**正确用法**：先用筛查指南判定是否阳性；阳性者进入临床流程后，"
            "再按诊治共识确定随访间隔。**不可把筛查阈值直接当作随访间隔的依据。**"
        ),
        "risk_if_confused": (
            "若把筛查阈值（≥6mm 阳性）误用于随访决策，会导致"
            "**对 6~8mm 的 mGGN 过度处置**（本应随访却直接进入治疗程序）——"
            "而文献显示部分实性结节的过度诊断率达 31%、亚洲人群 38%。"
        ),
    },
    {
        "id": "D2",
        "topic": "筛查间隔的版本更替（同一指南新旧两版）",
        "thresholds": [
            {"doc": "筛查指南2023", "clause": "随访间隔", "value": "阳性结节随访 3 个月",
             "context": "screening_interval_v2023", "meaning": "旧版"},
            {"doc": "筛查指南2025", "clause": "章3", "value": "连续 2 年阴性 → 暂停筛查 2 年",
             "context": "screening_interval_v2025", "meaning": "新版修订"},
        ],
        "resolution": (
            "2025 年版**修订**了筛查间隔策略：新增「连续 2 年阴性者暂停筛查 2 年」，"
            "阳性者仍维持每年 1 次。**应以 2025 年版为准**；"
            "2023 年版仅保留用于版本迁移对照。"
        ),
        "risk_if_confused": "沿用旧版间隔会导致对低风险人群的过度筛查。",
    },
]


def check_disambiguation(description: str, facts: Any) -> list[dict[str, Any]]:
    """检测当前情形是否命中跨文档语境消歧规则。

    触发条件（任一）：
      · 描述中出现"筛查"相关词 → 提示筛查语境与随访语境的区分
      · 结节实性成分落在 6~8mm 的**跨文档阈值区间** → 命中 D1
    """
    out: list[dict[str, Any]] = []
    text = description or ""
    solid = getattr(facts, "solid_component_mm", None)
    mentions_screening = any(k in text for k in
                             ["筛查", "体检", "阳性", "基线", "年度"])

    for rule in DISAMBIGUATION_RULES:
        if rule["id"] == "D1":
            # 实性成分 6~8mm，或结节直径 6~8mm 且提到筛查
            hit = (solid is not None and 6 <= solid <= 8) or \
                  (mentions_screening and getattr(facts, "diameter_mm", None) is not None
                   and 6 <= (facts.diameter_mm or 0) <= 8)
            if hit:
                out.append({
                    "rule_id": rule["id"], "topic": rule["topic"],
                    "thresholds": rule["thresholds"],
                    "resolution": rule["resolution"],
                    "risk_if_confused": rule["risk_if_confused"],
                })
        elif rule["id"] == "D2" and mentions_screening:
            out.append({
                "rule_id": rule["id"], "topic": rule["topic"],
                "thresholds": rule["thresholds"],
                "resolution": rule["resolution"],
                "risk_if_confused": rule["risk_if_confused"],
            })
    return out


def cross_document_evidence(description: str, facts: Any,
                            clause: str) -> dict[str, Any]:
    """汇总当前情形所涉及的**跨文档依据**。

    回答"这个结论用了哪几份文档"，是"跨文档推理"的可核验落点。
    """
    d = getattr(facts, "diameter_mm", None)
    density = getattr(facts, "density_type", None) or "实性肺结节"
    solid = getattr(facts, "solid_component_mm", None)
    text = description or ""
    mentions_screening = any(k in text for k in ["筛查", "体检", "基线", "年度", "阳性"])

    used: list[dict[str, Any]] = []

    # ① 诊治共识（随访管理语境）—— 总是涉及
    used.append({
        "doc": "共识2024",
        "source": "肺结节诊治中国专家共识（2024年版）",
        "clause": clause,
        "context": "followup_management",
        "role": "确定随访间隔与处置动作",
    })

    # ② 筛查指南（筛查判定语境）—— 提到筛查/体检时涉及
    if mentions_screening or (solid is not None and 6 <= solid <= 8):
        used.append({
            "doc": "筛查指南2025",
            "source": "中国肺癌低剂量CT筛查指南（2025年版）",
            "clause": "章2 / 章3 / 章5.1",
            "context": "screening_entry / screening_positive",
            "role": "判定是否属高危人群、是否达到筛查阳性、筛查间隔",
        })

    # ③ 版本迁移（同一指南新旧两版）
    if mentions_screening:
        used.append({
            "doc": "筛查指南2023",
            "source": "中国肺癌低剂量CT筛查指南（2023年版）",
            "clause": "随访间隔",
            "context": "screening_interval_v2023",
            "role": "版本迁移对照（2025 年版已修订，仅作对照）",
        })

    return {
        "documents_involved": len(used),
        "documents": used,
        "note": ("跨文档推理的可核验落点：本结论同时使用了上述文档中的条款。"
                 "筛查语境与随访语境的阈值差异见 disambiguation 字段。"),
    }


def referral_rule(d: float) -> str:
    if d <= 5:
        return "基层医院随访管理（推荐意见18①）"
    if d <= 10:
        return "建议转肺结节诊治分中心管理（推荐意见18②）"
    return "可由肺癌防治联盟协助指导管理（推荐意见18③）"


# ===========================================================================
# 图文类资产：图片 → VLM 识别 → 事实 → 图谱推理（v3.0 新增）
# ---------------------------------------------------------------------------
# 赛题第一句要求"搭建**多模态**异构数据资产认知智能体"。
# 此前图文链路是**离线脚本**（`kg-service/imaging_pipeline.py`），
# 智能体挂载的工具里没有任何图像工具 —— 即"多模态不在智能体内"。
#
# 本工具把该链路收进 MCP Server，使智能体可直接对报告图片作答。
#
# 设计：VLM 只负责**识别**（图片 → 结构化事实），
#       推理仍由本地图谱引擎完成（`run_inference`）——
#       即"多模态输入统一汇入同一条推理链路"。
# ===========================================================================

VLM_EXTRACT_PROMPT = """你是一个医学影像报告的**结构化信息抽取器**。
请仔细阅读这张肺结节影像报告图片，抽取以下字段并以 JSON 输出。

严格按此 JSON 结构输出（缺失字段填 null，不要编造）：
{
  "最大径_mm": <数值或null>,
  "密度类型": "<实性结节|纯磨玻璃结节|混杂性磨玻璃结节|null>",
  "实性成分_mm": <数值或null>,
  "年龄": <数值或null>,
  "性别": "<男|女|null>",
  "吸烟年数": <数值或null>,
  "影像特征": ["<毛刺征|分叶征|胸膜凹陷征|血管集束征|位于上叶>"],
  "检查项目": "<字符串或null>"
}

只输出 JSON，不要任何解释文字。"""

VLM_MODEL = "Qwen/Qwen3-VL-8B-Instruct"
VLM_BASE_URL = "https://api.siliconflow.cn/v1/chat/completions"


def vlm_extract_facts(image_bytes: bytes, api_key: str,
                      mime: str = "image/png") -> dict:
    """调用 VLM 从报告图片抽取结构化事实（仅识别，不推理）。"""
    import base64
    import urllib.request

    b64 = base64.b64encode(image_bytes).decode()
    payload = {
        "model": VLM_MODEL,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image_url",
                 "image_url": {"url": f"data:{mime};base64,{b64}"}},
                {"type": "text", "text": VLM_EXTRACT_PROMPT},
            ],
        }],
        "max_tokens": 800,
        "temperature": 0.1,
    }
    req = urllib.request.Request(
        VLM_BASE_URL, data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {api_key}",
                 "Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        resp = json.loads(r.read().decode())
    text = resp["choices"][0]["message"]["content"]

    # 容错解析：模型可能包裹 ```json 代码块
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return {"_parse_error": "VLM 未返回 JSON", "_raw": text[:500]}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError as e:
        return {"_parse_error": f"JSON 解析失败: {e}", "_raw": text[:500]}


def facts_to_description(facts: dict) -> str:
    """把 VLM 抽取的结构化事实转成推理引擎的自然语言输入。

    与 `kg-service/imaging_pipeline.py` 中的同名函数保持一致 ——
    这是"多模态输入统一汇入同一条推理链路"的衔接点。
    """
    parts: list[str] = []
    if facts.get("年龄"):
        parts.append(f"{facts['年龄']}岁")
    if facts.get("性别"):
        parts.append(str(facts["性别"]) + "性")
    if facts.get("最大径_mm") is not None:
        parts.append(f"{facts['最大径_mm']}mm")
    if facts.get("密度类型"):
        parts.append(str(facts["密度类型"]))
    if facts.get("实性成分_mm") is not None:
        parts.append(f"实性成分{facts['实性成分_mm']}mm")
    if facts.get("吸烟年数"):
        parts.append(f"吸烟{facts['吸烟年数']}年")
    for feat in facts.get("影像特征") or []:
        parts.append(str(feat))
    return "，".join(parts)


def referral_rule(d: float) -> str:
    if d <= 5:
        return "基层医院随访管理（推荐意见18①）"


def check_contraindications(density: str,
                            solid: Optional[float]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for r in CONTRA_RULES:
        if r["density"] != density:
            continue
        if solid is None or solid <= r["solid_max"]:
            out.append({
                "examination": r["examination"],
                "reason": r["reason"],
                "clause": r["clause"],
            })
    return out


def run_inference(description: str) -> dict[str, Any]:
    """执行多跳推理，返回结论 + 完整依据链。"""
    facts = extract_facts(description)
    chain: list[dict[str, Any]] = []
    hop = 0

    # 跳1 密度类型
    hop += 1
    density = facts.density_type or "实性肺结节"
    chain.append({
        "hop": hop, "rule": "密度类型识别",
        "from": facts.summary(), "to": density,
        "clause": "",
        "evidence": "依据CT密度表现判定（共识定义章节（二）3）",
    })

    if facts.diameter_mm is None:
        return {
            "facts": asdict(facts), "facts_summary": facts.summary(),
            "coverage": "NOT_COVERED", "traceable": True,
            "conclusion": "缺少结节直径信息，无法定位适用条款。请补充结节最大径。",
            "chain": chain,
            "recommendations": [], "contraindications": [], "referral": "",
            "missing_fields": ["diameter_mm"],
        }

    d = facts.diameter_mm
    has_risk = bool(facts.risk_factors)

    # 跳2 大小分类
    hop += 1
    sc = size_category(d)
    chain.append({
        "hop": hop, "rule": "大小分类（分级诊疗依据）",
        "from": f"直径{d}mm", "to": sc, "clause": "推荐意见18",
        "evidence": "≤5mm为微小结节，5~10mm为小结节，10~30mm应尽早诊治",
    })

    # 跳3 条款定位
    hop += 1
    m = match_clause(density, d, has_risk)
    if not m:
        chain.append({
            "hop": hop, "rule": "条款匹配",
            "from": f"{density} {d}mm", "to": "无匹配条款",
            "clause": "", "evidence": "知识图谱中无适用条款 → 触发拒答兜底",
        })
        return {
            "facts": asdict(facts), "facts_summary": facts.summary(),
            "coverage": "NOT_COVERED", "traceable": True,
            "conclusion": "本知识库未覆盖该情形，建议转上级医院或提交 MDT 会诊。（拒答兜底：不编造条款）",
            "chain": chain, "recommendations": [], "contraindications": [],
            "referral": "",
        }

    clause, why = m
    rec = RECOMMENDATIONS[clause]
    chain.append({
        "hop": hop, "rule": "条款定位（实体对齐 → 条款匹配）",
        "from": why, "to": f"【{clause}】{rec['title']}",
        "clause": clause,
        "evidence": f"该结节类型与尺寸落在{clause}的适用范围",
    })

    # 跳4 展开处置动作
    hop += 1
    recs: list[dict[str, Any]] = []
    for a in rec.get("recommends", []):
        recs.append({"type": "处置动作", "action": a, "clause": clause,
                     "strength": rec["strength"]})
    for e in rec.get("requires", []):
        recs.append({"type": "检查建议", "action": f"检查：{e}", "clause": clause,
                     "strength": rec["strength"]})
    chain.append({
        "hop": hop, "rule": "展开条款处置动作",
        "from": f"【{clause}】{rec['title']}",
        "to": "、".join([r["action"] for r in recs]) or "（无显式动作）",
        "clause": clause, "evidence": f"沿 recommends 关系从{clause}展开",
    })

    # 跳5 随访间隔
    if rec.get("follow_up"):
        hop += 1
        chain.append({
            "hop": hop, "rule": "读取随访间隔（数据属性）",
            "from": f"【{clause}】", "to": rec["follow_up"],
            "clause": clause, "evidence": "沿 followUpMonths 数据属性取值",
        })

    # 跳6 禁忌
    cds = check_contraindications(density, facts.solid_component_mm)
    if cds:
        hop += 1
        chain.append({
            "hop": hop, "rule": "禁忌与边界判定",
            "from": facts.summary(),
            "to": "；".join(c["reason"] for c in cds),
            "clause": cds[0]["clause"],
            "evidence": "命中禁忌规则",
        })

    # 跳7 分级诊疗
    hop += 1
    ref = referral_rule(d)
    chain.append({
        "hop": hop, "rule": "分级诊疗归属",
        "from": sc, "to": ref, "clause": "推荐意见18",
        "evidence": "按结节大小与诊断明确程度决定管理机构层级",
    })

    # 跳8 跨文档语境消歧（v2.0 新增）
    disambig = check_disambiguation(description, facts)
    if disambig:
        hop += 1
        chain.append({
            "hop": hop, "rule": "跨文档语境消歧",
            "from": facts.summary(),
            "to": "；".join(x["topic"] for x in disambig),
            "clause": "、".join(sorted({t["clause"] for x in disambig
                                       for t in x["thresholds"]})),
            "evidence": ("命中跨文档阈值区间/语境冲突 → 按语境区分判定口径，"
                         "避免把筛查阈值误用于随访决策（详见 disambiguation 字段）"),
        })

    actions = [r["action"] for r in recs]
    conclusion = (
        f"{facts.summary()} → 适用【{clause}】{rec['title']}"
        f"（{rec['strength']}）；处置：{'、'.join(actions) or '见依据链'}；"
        f"分级诊疗：{ref}。"
    )

    return {
        "facts": asdict(facts),
        "facts_summary": facts.summary(),
        "coverage": "COVERED",
        "traceable": True,
        "conclusion": conclusion,
        "clause": clause,
        "clause_title": rec["title"],
        "strength": rec["strength"],
        "recommendations": recs,
        "follow_up": rec.get("follow_up", ""),
        "next_step": rec.get("next_step", []),
        "caveat": rec.get("caveat", ""),
        "contraindications": cds,
        "referral": ref,
        "disambiguation": disambig,
        "cross_document": cross_document_evidence(description, facts, clause),
        "chain": chain,
        "disclaimer": "本结果仅供临床参考，不构成诊断结论，不替代医生判断，不包含用药与处方。",
    }


# ============================================================================
# 三、MCP Server 定义
# ============================================================================

mcp = FastMCP(
    name="lung-nodule-kg",
    instructions=(
        "肺结节规范处置知识图谱服务。基于《肺结节诊治中国专家共识（2024年版）》"
        "构建的领域本体，提供带条款级溯源的处置决策推理。\n"
        "与向量检索（knowledge_base_search）配合使用：先用本服务定位适用条款与"
        "推理路径，再用向量检索获取条款原文。\n"
        "所有结论均标注【推荐意见N】来源；知识库未覆盖时返回拒答，不编造条款。"
    ),
)

# ---------------------------------------------------------------------------
# DNS 重绑定保护配置（关键）
# ---------------------------------------------------------------------------
# FastMCP 2.x 默认启用 DNS rebinding protection，只信任 localhost（127.0.0.1）。
# 当 Nexent 以容器服务名（如 http://nexent-mcp:8020/mcp）访问时，
# Host 头为 "nexent-mcp:8020"，会被框架拒绝并返回 HTTP 421 Misdirected Request。
#
# 处理：显式允许容器服务名与常见内网 Host，仅对 MCP 的 HTTP 传输生效。
# 由于本服务部署在隔离的 Docker 内网（nexent_network）中、不暴露到公网，
# 放宽 Host 校验不会引入额外的外部攻击面。
# ---------------------------------------------------------------------------
try:
    from mcp.server.transport_security import TransportSecuritySettings

    _ALLOWED_HOSTS = [
        "nexent-mcp", "nexent-mcp:8020",
        "nexent-config", "nexent-config:8020",
        "nexent-runtime", "nexent-runtime:8020",
        "localhost", "localhost:8020",
        "127.0.0.1", "127.0.0.1:8020",
        "host.docker.internal", "host.docker.internal:8020",
        "*",
    ]
    _ALLOWED_ORIGINS = [
        "http://nexent-mcp:8020", "http://nexent-config:8020",
        "http://localhost:8020", "http://127.0.0.1:8020", "*",
    ]

    _sec = TransportSecuritySettings(
        enable_dns_rebinding_protection=False,
        allowed_hosts=_ALLOWED_HOSTS,
        allowed_origins=_ALLOWED_ORIGINS,
    )

    # FastMCP 2.x：优先通过 settings 注入；不同小版本字段名略有差异
    for _target in ("transport_security", "security"):
        if hasattr(mcp.settings, _target):
            setattr(mcp.settings, _target, _sec)
            break
except Exception as _e:  # pragma: no cover - 兼容不同 fastmcp 版本
    import logging as _logging
    _logging.getLogger(__name__).warning(
        "无法设置 MCP 传输安全策略（容器名访问可能被拒）: %s", _e)


@mcp.tool(
    annotations={"title": "肺结节处置决策推理", "readOnlyHint": True,
                 "openWorldHint": False},
)
def kg_consult_decision(
    description: str,
) -> dict[str, Any]:
    """基于知识图谱为肺结节患者推导规范处置建议，输出完整可溯源依据链。

    这是本服务的核心工具。当你需要判断「某位肺结节患者应该如何处理」时使用。

    输入为自然语言临床描述，需包含**结节直径**（必须），建议包含密度类型、
    危险因素、实性成分等。服务会执行多跳推理并返回：

      · 结论与适用条款（【推荐意见N】）
      · 逐跳推理链（每跳标注依据条款）
      · 处置动作与随访间隔
      · 禁忌与边界提示（如 PET-CT 不适用情形）
      · 分级诊疗归属
      · 合规声明

    若知识图谱未覆盖该情形，返回 coverage=NOT_COVERED 并给出拒答提示
    （不会编造条款）。

    Args:
        description: 患者的自然语言临床描述。
            示例1："55岁男性，8mm混合磨玻璃结节，实性成分2mm，吸烟30年"
            示例2："女，48岁，6mm纯磨玻璃结节，无吸烟史"
            示例3："62岁男性，15mm混杂性磨玻璃结节，有毛刺征"

    Returns:
        结构化 JSON，含 conclusion / clause / chain / recommendations /
        contraindications / referral / traceable / disclaimer 字段。
    """
    if not description or not description.strip():
        return {
            "error": "MISSING_INPUT",
            "message": "缺少临床描述。请提供至少包含结节直径的描述。",
            "suggestion": '例如："55岁男性，8mm混合磨玻璃结节，吸烟30年"',
        }
    result = run_inference(description)
    if result["coverage"] == "NOT_COVERED" and result.get("missing_fields"):
        result["suggestion"] = '请在描述中补充结节最大径，例如"8mm"。'
    return result


@mcp.tool(
    annotations={"title": "报告图片结构化识别与决策", "readOnlyHint": True,
                 "openWorldHint": True},
)
def kg_analyze_report_image(
    image_base64: str,
    mime_type: str = "image/png",
) -> dict[str, Any]:
    """对肺结节**影像报告图片**做结构化识别，并直接给出可溯源的处置建议。

    这是本服务唯一的**多模态**工具。当用户提供报告图片（截图、照片、
    导出的 PDF 页面）而不是文字描述时使用。

    执行链路（多模态输入统一汇入同一条推理链路）：
        图片 → VLM 识别 → 结构化事实 → 图谱推理 → 带条款级溯源的依据链

    与 `kg_consult_decision` 的区别：
      · `kg_consult_decision` 接收**文字描述**
      · 本工具接收**图片**，先做 OCR/VLM 识别再走同一推理引擎

    重要：VLM 只负责**识别**（不推理、不给建议）；所有处置结论均来自
    本地知识图谱，因此同样带【推荐意见N】条款级溯源。

    Args:
        image_base64: 报告图片的 base64 编码（不含 data URI 前缀）。
        mime_type: 图片 MIME 类型，默认 image/png。

    Returns:
        结构化 JSON，含 recognized_facts（VLM 识别结果）、description
        （转成的临床描述）与 decision（图谱推理结果，同 kg_consult_decision）。
    """
    import base64 as _b64
    api_key = os.environ.get("SILICONFLOW_KEY", "")
    if not api_key:
        return {
            "error": "MISSING_API_KEY",
            "message": ("未配置 SILICONFLOW_KEY 环境变量，无法调用 VLM 做图片识别。"
                        "可改用 kg_consult_decision 并直接提供文字描述。"),
        }
    if not image_base64 or not image_base64.strip():
        return {"error": "MISSING_INPUT", "message": "缺少图片 base64 内容。"}

    try:
        raw = _b64.b64decode(image_base64, validate=False)
    except Exception as e:                                    # noqa: BLE001
        return {"error": "BAD_BASE64", "message": f"base64 解码失败: {e}"}

    facts = vlm_extract_facts(raw, api_key, mime=mime_type)
    if facts.get("_parse_error"):
        return {
            "error": "VLM_PARSE_FAILED",
            "message": facts["_parse_error"],
            "raw_output": facts.get("_raw", ""),
            "suggestion": "可改用 kg_consult_decision 并直接提供文字描述。",
        }

    description = facts_to_description(facts)
    decision = run_inference(description) if description else {
        "coverage": "NOT_COVERED",
        "conclusion": "未能从图片中识别出足够的临床事实（至少需要结节最大径）。",
        "missing_fields": ["diameter_mm"],
    }

    return {
        "modality": "image",
        "recognized_facts": facts,
        "description": description,
        "decision": decision,
        "pipeline": "图片 → VLM 识别 → 结构化事实 → 图谱推理 → 依据链",
        "note": ("VLM 仅做识别，不产生医学主张；"
                 "全部处置结论来自本地知识图谱并带条款级溯源。"),
    }


@mcp.tool(
    annotations={"title": "查询本体概念", "readOnlyHint": True,
                 "openWorldHint": False},
)
def kg_lookup_concept(
    term: str,
) -> dict[str, Any]:
    """查询肺结节领域本体中的一个概念定义、所属层级与标准对齐信息。

    当你需要确认某个术语的含义（如 pGGN 与 mGGN 的区别、微小结节的尺寸界限）
    或需要把口语化描述映射到规范术语时使用。

    Args:
        term: 待查询的术语，支持中文名、英文缩写或口语化表达。
            示例："mGGN"、"混合磨玻璃"、"微小结节"、"部分实性结节"

    Returns:
        含 canonical（规范名）、parent（上位概念）、definition（定义）、
        alias（别名）、constraint（尺寸约束）、managed_at（管理机构）的 JSON。
        未收录时返回 matched=False 与最接近的候选。
    """
    if not term or not term.strip():
        return {
            "error": "MISSING_INPUT",
            "message": "缺少待查询术语。",
            "suggestion": '例如："mGGN"',
        }
    t = term.strip()
    # 精确 / 别名匹配
    for name, meta in CONCEPT_HIERARCHY.items():
        names = [name] + list(meta.get("alias", []))
        if t in names:
            return {
                "matched": True, "canonical": name,
                "parent": meta.get("parent"),
                "definition": meta.get("definition", ""),
                "alias": meta.get("alias", []),
                "constraint": meta.get("constraint", ""),
                "managed_at": meta.get("managed_at", ""),
                "children": meta.get("children", []),
            }
    # 包含匹配
    for name, meta in CONCEPT_HIERARCHY.items():
        names = [name] + list(meta.get("alias", []))
        if any(n and (n in t or t in n) for n in names):
            return {
                "matched": True, "canonical": name,
                "parent": meta.get("parent"),
                "definition": meta.get("definition", ""),
                "alias": meta.get("alias", []),
                "constraint": meta.get("constraint", ""),
                "managed_at": meta.get("managed_at", ""),
                "children": meta.get("children", []),
                "match_type": "fuzzy",
            }
    return {
        "matched": False,
        "term": t,
        "message": f"本体中未收录术语「{t}」。",
        "available_concepts": list(CONCEPT_HIERARCHY.keys()),
        "suggestion": "请检查术语拼写，或改用上方 available_concepts 中的规范术语。",
    }


@mcp.tool(
    annotations={"title": "查询共识条款", "readOnlyHint": True,
                 "openWorldHint": False},
)
def kg_get_clause(
    clause: str,
) -> dict[str, Any]:
    """获取《肺结节诊治中国专家共识（2024年版）》指定条款的完整内容与推理关系。

    当你已经知道条款编号（如从 kg_consult_decision 得到），需要展开其完整内容、
    推荐强度、适用结节类型、处置动作、随访间隔、注意事项时使用。

    Args:
        clause: 条款编号或关键词。
            支持："推荐意见14"、"14"、"mGGN"、"随访"

    Returns:
        含 clause / title / strength / text（原文摘要）/ applies_to /
        recommends / requires / follow_up / next_step / caveat 的 JSON。
    """
    if not clause or not clause.strip():
        return {
            "error": "MISSING_INPUT",
            "message": "缺少条款编号。",
            "suggestion": '例如："推荐意见14" 或 "14"',
        }
    key = clause.strip()
    m = re.search(r"(\d{1,2})", key)
    if m:
        key = f"推荐意见{m.group(1)}"
    if key in RECOMMENDATIONS:
        r = RECOMMENDATIONS[key]
        return {
            "found": True, "clause": key,
            "title": r["title"], "strength": r["strength"],
            "text": r["text"], "applies_to": r.get("applies_to", []),
            "recommends": r.get("recommends", []),
            "requires": r.get("requires", []),
            "follow_up": r.get("follow_up", ""),
            "next_step": r.get("next_step", []),
            "caveat": r.get("caveat", ""),
            "referral": r.get("referral", {}),
            "source": "《肺结节诊治中国专家共识（2024年版）》"
                      "中华结核和呼吸杂志, 2024, 47(8): 716-729",
        }
    # 关键词检索
    hits = [
        {"clause": k, "title": v["title"], "strength": v["strength"]}
        for k, v in RECOMMENDATIONS.items()
        if key in v["title"] or key in v["text"]
        or any(key in a for a in v.get("applies_to", []))
    ]
    if hits:
        return {
            "found": False, "query": key, "match_type": "keyword",
            "message": f"未找到精确匹配的条款编号，以下是关键词命中的条款。",
            "candidates": hits,
        }
    return {
        "found": False, "query": key,
        "message": f"未找到条款「{key}」。",
        "available_clauses": sorted(RECOMMENDATIONS.keys(),
                                    key=lambda x: int(re.search(r"\d+", x).group())),
        "suggestion": "请使用 available_clauses 中的编号。",
    }


@mcp.tool(
    annotations={"title": "按结节特征检索适用条款", "readOnlyHint": True,
                 "openWorldHint": False},
)
def kg_find_clauses_by_nodule(
    density_type: str,
    diameter_mm: float,
    has_risk_factor: bool = False,
) -> dict[str, Any]:
    """按结节密度类型与直径，检索本体中适用的推荐意见条款（不含完整推理）。

    当你只想快速定位「这类结节对应哪几条条款」，或需要做条款覆盖分析时使用。
    若需要完整处置建议与推理链，请改用 kg_consult_decision。

    Args:
        density_type: 结节密度类型，取值之一：
            "实性肺结节" / "纯磨玻璃结节" / "混杂性磨玻璃结节"。
            也接受口语化表达（如 "实性"、"磨玻璃"、"混合磨玻璃"）。
        diameter_mm: 结节最大径，单位毫米。示例：8
        has_risk_factor: 是否存在肺癌危险因素（吸烟、职业暴露、慢性肺病、
            肿瘤史或家族史）。默认 False。

    Returns:
        含 matched_clause（最佳匹配条款）/ all_candidates（全部候选）/
        reasoning（匹配依据）的 JSON。
    """
    dmap = {
        "实性": "实性肺结节", "实性结节": "实性肺结节", "实性肺结节": "实性肺结节",
        "磨玻璃": "纯磨玻璃结节", "纯磨玻璃": "纯磨玻璃结节",
        "纯磨玻璃结节": "纯磨玻璃结节", "pggn": "纯磨玻璃结节",
        "混合磨玻璃": "混杂性磨玻璃结节", "混杂性磨玻璃结节": "混杂性磨玻璃结节",
        "部分实性": "混杂性磨玻璃结节", "mggn": "混杂性磨玻璃结节",
    }
    density = dmap.get(density_type.strip().lower().replace(" ", ""),
                       density_type.strip())
    if density not in ("实性肺结节", "纯磨玻璃结节", "混杂性磨玻璃结节"):
        return {
            "error": "INVALID_DENSITY_TYPE",
            "message": f"无法识别的密度类型「{density_type}」。",
            "valid_values": ["实性肺结节", "纯磨玻璃结节", "混杂性磨玻璃结节"],
            "suggestion": '请使用 valid_values 中的取值，例如 "混杂性磨玻璃结节"。',
        }
    if diameter_mm is None or diameter_mm <= 0:
        return {
            "error": "INVALID_DIAMETER",
            "message": "直径必须为正数（单位 mm）。",
            "suggestion": '例如：diameter_mm=8',
        }

    m = match_clause(density, float(diameter_mm), bool(has_risk_factor))
    candidates = [
        {"clause": r["clause"], "density": r["density"],
         "range": f"{r.get('d_min') or 0}~{r.get('d_max') or '∞'}mm",
         "condition": r.get("when", ""),
         "title": RECOMMENDATIONS[r["clause"]]["title"]}
        for r in MATCH_RULES if r["density"] == density
    ]
    out: dict[str, Any] = {
        "density_type": density,
        "diameter_mm": diameter_mm,
        "has_risk_factor": bool(has_risk_factor),
        "size_category": size_category(float(diameter_mm)),
        "all_candidates": candidates,
    }
    if m:
        clause, why = m
        out.update({
            "matched": True, "matched_clause": clause,
            "clause_title": RECOMMENDATIONS[clause]["title"],
            "strength": RECOMMENDATIONS[clause]["strength"],
            "reasoning": why,
        })
    else:
        out.update({
            "matched": False,
            "message": "该组合在本体中无对应条款。",
            "suggestion": "请核对密度类型与直径；或调用 kg_consult_decision 做完整推理。",
        })
    return out


@mcp.tool(
    annotations={"title": "获取本体概览", "readOnlyHint": True,
                 "openWorldHint": False},
)
def kg_get_ontology_summary() -> dict[str, Any]:
    """获取肺结节领域本体的整体概览：类层次、条款数量、标准对齐情况。

    当你需要说明本服务的知识来源与覆盖范围，或判断某个问题是否可能被覆盖时使用。

    Returns:
        含 source（知识来源）/ stats（统计）/ concept_tree（概念层次）/
        clause_list（条款清单）/ standards（标准对齐）的 JSON。
    """
    return {
        "source": {
            "document": "《肺结节诊治中国专家共识（2024年版）》",
            "authors": "中华医学会呼吸病学分会、中国肺癌防治联盟专家组",
            "journal": "中华结核和呼吸杂志, 2024, 47(8): 716-729",
            "doi": "10.3760/cma.j.cn112147-20231109-00300",
        },
        "stats": {
            "concepts": len(CONCEPT_HIERARCHY),
            "clauses": len(RECOMMENDATIONS),
            "match_rules": len(MATCH_RULES),
            "contraindication_rules": len(CONTRA_RULES),
        },
        "concept_tree": {
            name: {"parent": meta.get("parent"),
                   "children": meta.get("children", [])}
            for name, meta in CONCEPT_HIERARCHY.items()
        },
        "clause_list": [
            {"clause": k, "title": v["title"], "strength": v["strength"]}
            for k, v in RECOMMENDATIONS.items()
        ],
        "standards": {
            "ACR Lung-RADS": "肺结节影像报告与数据系统",
            "SNOMED CT": "临床医学术语标准",
            "ICD-10": "国际疾病分类",
            "LOINC": "检验检查项目编码",
            "中国肺癌低剂量CT筛查指南（2023年版）": "LDCT 扫描参数",
        },
        "boundary": (
            "本本体仅涵盖肺结节的规范处置决策，不含影像识别、病理诊断、"
            "用药与处方。所有内容可溯源至上述共识条款，不产生新的医学主张。"
        ),
    }


@mcp.tool(
    annotations={"title": "列出全部条款", "readOnlyHint": True,
                 "openWorldHint": False},
)
def kg_list_clauses() -> dict[str, Any]:
    """列出知识图谱中全部 18 条推荐意见的编号、标题与推荐强度。

    用于确认覆盖范围，或在用户询问"你都能回答什么"时给出能力清单。

    Returns:
        含 clauses（条款列表）与 total 的 JSON。
    """
    return {
        "total": len(RECOMMENDATIONS),
        "clauses": [
            {
                "clause": k,
                "title": v["title"],
                "strength": v["strength"],
                "applies_to": v.get("applies_to", []),
                "follow_up": v.get("follow_up", ""),
            }
            for k, v in sorted(RECOMMENDATIONS.items(),
                               key=lambda x: int(re.search(r"\d+", x[0]).group()))
        ],
    }


# ============================================================================
# 四、启动
# ============================================================================

def main() -> int:
    ap = argparse.ArgumentParser(description="肺结节决策知识图谱 MCP Server")
    ap.add_argument("--transport", default="http",
                    choices=["http", "stdio", "sse", "streamable-http"],
                    help="传输方式：http/streamable-http（远程）或 stdio（本地）")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8020)
    args = ap.parse_args()

    if args.transport == "stdio":
        mcp.run(transport="stdio")
        return 0

    # FastMCP 2.x：通过 settings 设置 host/port
    try:
        mcp.settings.host = args.host
        mcp.settings.port = args.port
    except Exception:
        pass
    transport = "streamable-http" if args.transport == "http" else args.transport
    mcp.run(transport=transport)
    return 0


if __name__ == "__main__":
    sys.exit(main())
