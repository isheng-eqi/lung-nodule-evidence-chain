#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
肺结节决策知识图谱服务（多跳推理引擎）
================================================================

对应赛题要求：
  "深度集成 Nexent 的 MCP 协议与 Skills 编排能力，
   打造'检索-推理'双驱动协同智能体执行流。"
  "挖掘行业沉睡存量数据资产，实现跨文档多跳知识推理、决策链路可溯源。"

设计：为什么需要图谱？（这是"为什么不用纯 RAG"的答案）
----------------------------------------------------------------
  纯向量检索只能回答「哪段文字最像这个问题」；
  本引擎回答「**沿着规则链推导，这个患者应该做什么、依据是哪一条**」。

  示例推理链（4 跳）：
    患者事实(8mm 混合磨玻璃 + 吸烟30年)
      →① 匹配密度类型      → mGGN(混杂性磨玻璃结节)
      →② 匹配大小分类      → ≤8mm 落在 mGGN 分支
      →③ 定位适用条款      → 【推荐意见14】
      →④ 展开条款的处置动作 → 3、6、12、24 个月 CT 随访
                            + AI 与人机 MDT 评估
      →⑤ 附加边界判定      → PET-CT 不适用(实性成分≤8mm)【推荐意见15】①
      →⑥ 分级诊疗归属      → 5~10mm 且未明确诊断 → 转分中心【推荐意见18】

  每一跳都可输出证据，实现「决策链路可溯源」。

存储：轻量三元组 + 内存索引（不依赖图数据库，符合 Nexent 依赖约束）
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from typing import Any, Optional


# ============================================================================
# 一、知识图谱存储
# ============================================================================

@dataclass
class Triple:
    subject: str
    predicate: str
    object: str
    clause: str = ""        # 溯源条款编号
    strength: str = ""      # 推荐强度
    kind: str = "object"    # object | data


class KnowledgeGraph:
    """轻量三元组知识图谱（SPO 索引 + 多跳遍历）。"""

    def __init__(self) -> None:
        self.triples: list[Triple] = []
        self._spo: dict[str, dict[str, list[Triple]]] = {}
        self._pos: dict[str, dict[str, list[Triple]]] = {}

    def add(self, t: Triple) -> None:
        self.triples.append(t)
        self._spo.setdefault(t.subject, {}).setdefault(t.predicate, []).append(t)
        self._pos.setdefault(t.predicate, {}).setdefault(t.object, []).append(t)

    def add_many(self, ts: list[Triple]) -> None:
        for t in ts:
            self.add(t)

    # ---- 基础查询 ----
    def objects(self, subject: str, predicate: str = "") -> list[Triple]:
        d = self._spo.get(subject, {})
        if predicate:
            return d.get(predicate, [])
        return [t for lst in d.values() for t in lst]

    def subjects(self, predicate: str, obj: str) -> list[Triple]:
        return self._pos.get(predicate, {}).get(obj, [])

    # ---- 多跳遍历 ----
    def multi_hop(self, start: str, path: list[str],
                  max_results: int = 50) -> list[list[Triple]]:
        """沿指定关系序列遍历，返回所有可达路径。

        path 例：["appliesTo", "recommends"] 表示
                start --appliesTo--> X --recommends--> Y
        """
        frontier: list[tuple[str, list[Triple]]] = [(start, [])]
        for rel in path:
            nxt: list[tuple[str, list[Triple]]] = []
            for node, acc in frontier:
                for t in self.objects(node, rel):
                    nxt.append((t.object, acc + [t]))
                    if len(nxt) >= max_results:
                        break
                if len(nxt) >= max_results:
                    break
            frontier = nxt
            if not frontier:
                break
        return [acc for _, acc in frontier]

    # ---- 反向：从处置动作回溯到条款 ----
    def trace_back(self, action: str) -> list[Triple]:
        return self.subjects("recommends", action)

    def stats(self) -> dict[str, Any]:
        return {
            "triples": len(self.triples),
            "subjects": len(self._spo),
            "predicates": len(self._pos),
            "object_triples": sum(1 for t in self.triples if t.kind == "object"),
            "data_triples": sum(1 for t in self.triples if t.kind == "data"),
        }


# ============================================================================
# 二、患者事实抽取（从自然语言描述 → 结构化事实）
# ============================================================================

@dataclass
class PatientFacts:
    """从临床描述中抽取的患者事实。"""
    raw: str = ""
    age: Optional[int] = None
    diameter_mm: Optional[float] = None
    solid_component_mm: Optional[float] = None
    density_type: str = ""          # 实性 / 纯磨玻璃 / 混杂性磨玻璃
    smoking_years: Optional[int] = None
    smoking_index: Optional[int] = None
    risk_factors: list[str] = field(default_factory=list)
    imaging_features: list[str] = field(default_factory=list)
    is_solitary: bool = True

    def summary(self) -> str:
        parts = []
        if self.diameter_mm is not None:
            parts.append(f"直径 {self.diameter_mm}mm")
        if self.density_type:
            parts.append(self.density_type)
        if self.age is not None:
            parts.append(f"{self.age} 岁")
        if self.smoking_years:
            parts.append(f"吸烟 {self.smoking_years} 年")
        if self.solid_component_mm is not None:
            parts.append(f"实性成分 {self.solid_component_mm}mm")
        return "、".join(parts) if parts else "（未识别到结构化事实）"


class FactExtractor:
    """从中文临床描述中抽取患者事实（规则 + 词典）。"""

    DENSITY_PATTERNS = [
        ("混杂性磨玻璃结节", r"混合磨玻璃|混杂性?(?:磨玻璃)?结节|部分实性|mGGN|混杂密度"),
        ("纯磨玻璃结节",     r"纯磨玻璃|磨玻璃结节|磨玻璃影|pGGN|GGO"),
        ("实性肺结节",       r"实性结节|实性肺结节|solid nodule"),
    ]
    RISK_PATTERNS = [
        ("吸烟史",            r"吸烟|抽烟|烟龄|包年|年支"),
        ("环境或高危职业暴露史", r"石棉|铍|铀|氡|职业暴露|粉尘"),
        ("慢性肺部疾病史",     r"慢阻肺|COPD|肺纤维化|肺结核|慢性肺病|肺气肿"),
        ("肿瘤史或家族史",     r"肿瘤史|癌症史|家族史|恶性肿瘤"),
    ]
    IMAGING_PATTERNS = [
        ("毛刺征",    r"毛刺"),
        ("分叶征",    r"分叶"),
        ("胸膜凹陷征", r"胸膜凹陷"),
        ("血管集束征", r"血管集束"),
        ("位于上叶",   r"上叶"),
        ("密度增加",   r"密度(?:增高|增加|升高)"),
        ("实性成分增多", r"实性成分(?:增多|增加|出现)"),
    ]

    def extract(self, text: str) -> PatientFacts:
        f = PatientFacts(raw=text)

        m = re.search(r"(\d{1,3})\s*岁", text)
        if m:
            f.age = int(m.group(1))

        m = re.search(r"(\d+(?:\.\d+)?)\s*mm", text)
        if m:
            f.diameter_mm = float(m.group(1))

        m = re.search(r"实性成分\s*(?:约|为|是)?\s*(\d+(?:\.\d+)?)\s*mm", text)
        if m:
            f.solid_component_mm = float(m.group(1))

        m = re.search(r"吸烟\s*(\d{1,3})\s*年", text)
        if m:
            f.smoking_years = int(m.group(1))
        m = re.search(r"(\d{2,4})\s*(?:年支|包年)", text)
        if m:
            f.smoking_index = int(m.group(1))

        for name, pat in self.DENSITY_PATTERNS:
            if re.search(pat, text):
                f.density_type = name
                break

        for name, pat in self.RISK_PATTERNS:
            if re.search(pat, text):
                f.risk_factors.append(name)

        for name, pat in self.IMAGING_PATTERNS:
            if re.search(pat, text):
                f.imaging_features.append(name)

        if re.search(r"多发|多个|两枚|三枚", text):
            f.is_solitary = False

        return f


# ============================================================================
# 三、推理引擎（检索-推理双驱动中的"推理"）
# ============================================================================

@dataclass
class InferenceStep:
    """推理链上的一跳。"""
    hop: int
    rule: str               # 本跳用到的规则描述
    from_state: str
    to_state: str
    clause: str = ""        # 溯源条款
    evidence: str = ""      # 依据说明


@dataclass
class InferenceResult:
    """推理结果：结论 + 完整依据链。"""
    facts: PatientFacts
    conclusion: str = ""
    recommendations: list[dict] = field(default_factory=list)
    chain: list[InferenceStep] = field(default_factory=list)
    contraindications: list[str] = field(default_factory=list)
    referral: str = ""
    traceable: bool = False
    coverage: str = ""      # COVERED / NOT_COVERED
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "facts": asdict(self.facts),
            "facts_summary": self.facts.summary(),
            "conclusion": self.conclusion,
            "recommendations": self.recommendations,
            "chain": [asdict(s) for s in self.chain],
            "contraindications": self.contraindications,
            "referral": self.referral,
            "traceable": self.traceable,
            "coverage": self.coverage,
            "notes": self.notes,
        }


class ReasoningEngine:
    """基于知识图谱的多跳推理引擎。"""

    def __init__(self, kg: KnowledgeGraph) -> None:
        self.kg = kg

    def infer(self, text: str) -> InferenceResult:
        facts = FactExtractor().extract(text)
        res = InferenceResult(facts=facts)
        hop = 0

        # ---- 跳1：匹配密度类型 ----
        hop += 1
        density = facts.density_type
        if density:
            res.chain.append(InferenceStep(
                hop=hop, rule="密度类型识别",
                from_state=facts.summary(), to_state=density,
                evidence="依据结节在 CT 上的密度表现判定。共识定义章节（二）3。",
            ))
        else:
            res.notes.append("未识别到明确的密度类型，按实性结节路径处理。")
            density = "实性肺结节"

        # ---- 跳2：大小分类 ----
        hop += 1
        d = facts.diameter_mm
        if d is None:
            res.coverage = "NOT_COVERED"
            res.conclusion = "缺少结节直径信息，无法定位适用条款。请补充结节最大径。"
            return res
        if d <= 5:
            size_cls = "微小结节"
        elif d <= 10:
            size_cls = "小结节"
        else:
            size_cls = "较大结节"
        res.chain.append(InferenceStep(
            hop=hop, rule="大小分类（分级诊疗依据）",
            from_state=f"直径 {d}mm", to_state=size_cls,
            clause="推荐意见18",
            evidence=f"最大径≤5mm 为微小结节，5~10mm 为小结节，10~30mm 应尽早诊治。",
        ))

        # ---- 跳3：定位适用条款 ----
        hop += 1
        rec = self._match_recommendation(density, d, facts)
        if rec is None:
            res.coverage = "NOT_COVERED"
            res.conclusion = ("本知识库未覆盖该情形，建议转上级医院或提交 MDT 会诊。"
                              "（拒答兜底：不编造条款）")
            res.chain.append(InferenceStep(
                hop=hop, rule="条款匹配", from_state=f"{density} {d}mm",
                to_state="无匹配条款",
                evidence="知识图谱中无适用条款 → 触发拒答兜底。",
            ))
            res.traceable = True
            return res

        clause, clause_label, applies = rec
        res.chain.append(InferenceStep(
            hop=hop, rule="条款定位（实体对齐 → 条款匹配）",
            from_state=f"{density} + 直径{d}mm",
            to_state=clause_label, clause=clause,
            evidence=f"该结节类型与尺寸落在 {clause} 的适用范围：{applies}",
        ))

        # ---- 跳4：展开条款的处置动作 ----
        hop += 1
        actions = self.kg.objects(clause, "recommends")
        exams = self.kg.objects(clause, "requiresExamination")
        intervals = [t for t in self.kg.objects(clause, "followUpMonths")]
        strengths = self.kg.objects(clause, "hasStrength")

        for t in actions:
            res.recommendations.append({
                "action": t.object, "clause": clause,
                "strength": t.strength, "type": "处置动作",
            })
        for t in exams:
            res.recommendations.append({
                "action": f"检查：{t.object}", "clause": clause,
                "strength": t.strength, "type": "检查建议",
            })
        res.chain.append(InferenceStep(
            hop=hop, rule="展开条款处置动作",
            from_state=clause_label,
            to_state="、".join([t.object for t in actions] or ["（无显式动作）"]),
            clause=clause,
            evidence=f"沿 recommends 关系从 {clause} 展开。",
        ))

        # ---- 跳5：随访间隔（数据属性）----
        if intervals:
            hop += 1
            iv = "、".join(t.object for t in intervals)
            res.chain.append(InferenceStep(
                hop=hop, rule="读取随访间隔（数据属性）",
                from_state=clause_label,
                to_state=f"{iv} 个月", clause=clause,
                evidence="沿 followUpMonths 数据属性取值。",
            ))

        # ---- 跳6：禁忌与边界判定 ----
        hop += 1
        cd = self._check_contraindication(density, facts)
        if cd:
            res.contraindications.append(cd)
            res.chain.append(InferenceStep(
                hop=hop, rule="禁忌与边界判定",
                from_state=facts.summary(), to_state=cd,
                clause="推荐意见15",
                evidence="PET-CT 不推荐用于实性成分≤8mm 的混杂性病灶。",
            ))

        # ---- 跳7：分级诊疗归属 ----
        hop += 1
        ref = self._referral_rule(d)
        if ref:
            res.referral = ref
            res.chain.append(InferenceStep(
                hop=hop, rule="分级诊疗归属", from_state=size_cls,
                to_state=ref, clause="推荐意见18",
                evidence="按结节大小与诊断明确程度决定管理机构层级。",
            ))

        # ---- 收尾 ----
        res.coverage = "COVERED"
        res.traceable = True
        strength_txt = strengths[0].object if strengths else ""
        res.conclusion = (
            f"{facts.summary()} → 适用 {clause_label}"
            f"{'（' + strength_txt + '）' if strength_txt else ''}；"
            f"处置：{'、'.join([r['action'] for r in res.recommendations]) or '见依据链'}。"
        )
        return res

    # ---- 条款匹配规则（本体的核心推理规则）----
    def _match_recommendation(self, density: str, d: float,
                              facts: PatientFacts
                              ) -> Optional[tuple[str, str, str]]:
        """把 (密度类型, 直径) 映射到推荐意见条款。

        规则来源：共识五、六章的推荐意见 10~15。
        """
        if density == "混杂性磨玻璃结节":
            if d <= 8:
                return ("推荐意见14", "【推荐意见14】mGGN≤8mm",
                        "孤立性 mGGN 直径≤8 mm")
            return ("推荐意见15", "【推荐意见15】mGGN>8mm",
                    "孤立性 mGGN 直径>8 mm")

        if density == "纯磨玻璃结节":
            if d <= 5:
                return ("推荐意见12", "【推荐意见12】pGGN≤5mm",
                        "pGGN 直径≤5 mm")
            if d <= 10:
                return ("推荐意见13", "【推荐意见13】pGGN 5~10mm",
                        "pGGN 直径 5~10 mm")

        if density == "实性肺结节":
            if d > 8:
                return ("推荐意见5", "【推荐意见5】实性结节>8mm",
                        "孤立性不明原因结节直径>8 mm")
            has_risk = bool(facts.risk_factors)
            if has_risk:
                return ("推荐意见11", "【推荐意见11】≤8mm 有危险因素",
                        "存在一项或更多肺癌危险因素的直径≤8 mm 实性结节")
            return ("推荐意见10", "【推荐意见10】≤8mm 无危险因素",
                    "孤立性实性结节直径≤8 mm 且无肺癌危险因素")

        return None

    def _check_contraindication(self, density: str,
                                facts: PatientFacts) -> str:
        if density == "混杂性磨玻璃结节":
            sc = facts.solid_component_mm
            if sc is None or sc <= 8:
                return ("PET-CT 不适用于本例：实性成分≤8mm 的混杂性病灶"
                        "（【推荐意见15】①）")
        return ""

    @staticmethod
    def _referral_rule(d: float) -> str:
        if d <= 5:
            return "基层医院随访管理（【推荐意见18】①）"
        if d <= 10:
            return "建议转肺结节诊治分中心管理（【推荐意见18】②）"
        return "可由肺癌防治联盟协助指导管理（【推荐意见18】③）"


# ============================================================================
# 四、装配：从本体构建 JSON 载入三元组
# ============================================================================

def load_graph_from_built(built_json_path: str,
                          triples_jsonl_path: str) -> KnowledgeGraph:
    """从 ontology_builder 的产物装配知识图谱。"""
    kg = KnowledgeGraph()
    with open(triples_jsonl_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            t = json.loads(line)
            # 对象属性用对齐后的本体概念；数据属性保留原值
            obj = t.get("align_target") or t["object"]
            if t.get("kind") == "object" and not t.get("aligned"):
                continue          # 未对齐的不入库（可拒绝的强制对齐）
            kg.add(Triple(
                subject=t["subject"], predicate=t["relation"], object=obj,
                clause=t.get("clause", ""), strength=t.get("strength", ""),
                kind=t.get("kind", "object"),
            ))
    return kg


# ============================================================================
# CLI 演示
# ============================================================================

def _demo() -> None:
    import sys
    triples_path = sys.argv[1] if len(sys.argv) > 1 else "triples.jsonl"
    kg = load_graph_from_built("built.json", triples_path)
    engine = ReasoningEngine(kg)

    cases = [
        "一位55岁男性，8mm混合磨玻璃结节，实性成分2mm，吸烟30年，该怎么随访？",
        "女，48岁，右肺上叶6mm纯磨玻璃结节，无吸烟史，如何处理？",
        "男，62岁，15mm混杂性磨玻璃结节，吸烟40年，有毛刺征。",
        "男，58岁，5mm实性结节，吸烟25年。",
        "患者45岁，7mm实性结节，无吸烟史，无其他危险因素。",
    ]

    print("=" * 72)
    print("  肺结节决策知识图谱 · 多跳推理演示")
    print("=" * 72)
    print(f"  图谱规模: {kg.stats()}")
    for i, c in enumerate(cases, 1):
        r = engine.infer(c)
        print("\n" + "-" * 72)
        print(f"【病例 {i}】{c}")
        print("-" * 72)
        print(f"  结论    : {r.conclusion}")
        print(f"  覆盖率  : {r.coverage}    可溯源: {r.traceable}")
        if r.referral:
            print(f"  分级诊疗: {r.referral}")
        if r.contraindications:
            for cd in r.contraindications:
                print(f"  禁忌    : {cd}")
        if r.notes:
            for n in r.notes:
                print(f"  提示    : {n}")
        print("  推理链:")
        for s in r.chain:
            cl = f" [{s.clause}]" if s.clause else ""
            print(f"    跳{s.hop} · {s.rule}{cl}")
            print(f"         {s.from_state}  →  {s.to_state}")
    print("\n" + "=" * 72)


if __name__ == "__main__":
    _demo()
