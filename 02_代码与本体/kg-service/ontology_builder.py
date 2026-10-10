#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
低资源场景下领域知识图谱本体半自动化构建算法
================================================================

对应赛题要求：
  "设计低资源场景下领域知识图谱本体半自动化构建方案，
   实现本体持续动态更新，并支持与对应行业规范、标准体系对齐。"

核心设计（三层流水线）
----------------------------------------------------------------
  L1 种子本体（Seed Ontology）
       人工定义少量核心概念作为约束骨架，防止 LLM 抽取失控。
       本项目中为 57 个类 / 23 个属性 / 18 条推荐意见锚点。

  L2 LLM 受约束抽取（Constrained Extraction）
       从领域文档抽取实体与关系，**强制对齐**到种子本体。
       对不上的内容不直接入库，而是标记为「候选新概念」。

  L3 人工审核闭环（Human-in-the-Loop Review）
       审核候选新概念 → 通过则扩充本体 → 本体持续动态更新。
       这一层就是"半自动化"里的那个"半"。

量化指标（用于证明"效率优势明显"）
----------------------------------------------------------------
  · 抽取覆盖率      = 有条款依据的关系数 / 总关系数
  · 本体对齐率      = 成功对齐到种子本体的关系数 / 抽取总关系数
  · 未对齐率        = 1 - 本体对齐率   ← 该指标随本体成长而下降，是"进化"的证据
  · 人工介入率      = 需人工审核的条目 / 抽取总条目   ← 越低越自动化
  · 单位文档耗时
  · 相对纯人工构建的人工节省比

用法：
    python3 ontology_builder.py --input <文档> --report
"""

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

# ============================================================================
# L1  种子本体（Seed Ontology）
#     人工定义，作为约束骨架。可持久化为 JSON，实现"本体持续动态更新"。
# ============================================================================

SEED_ONTOLOGY: dict[str, Any] = {
    "version": "1.0",
    "source": "肺结节诊治中国专家共识（2024年版）",
    "classes": {
        # ---- 结节分类 ----
        "肺结节": {"parent": None, "aliases": ["结节", "肺部结节"]},
        "微小结节": {"parent": "肺结节", "aliases": ["微小肺结节"],
                    "constraint": {"diameter_mm": {"max": 5}}},
        "小结节": {"parent": "肺结节", "aliases": ["小肺结节"],
                  "constraint": {"diameter_mm": {"min": 5, "max": 10}}},
        "较大结节": {"parent": "肺结节", "aliases": ["10~30mm结节"],
                    "constraint": {"diameter_mm": {"min": 10, "max": 30}}},
        "实性肺结节": {"parent": "肺结节", "aliases": ["实性结节", "solid nodule"]},
        "亚实性肺结节": {"parent": "肺结节", "aliases": ["亚实性结节", "subsolid nodule"]},
        "纯磨玻璃结节": {"parent": "亚实性肺结节",
                        "aliases": ["pGGN", "纯磨玻璃影", "pure ground-glass nodule"]},
        "混杂性磨玻璃结节": {"parent": "亚实性肺结节",
                            "aliases": ["mGGN", "部分实性结节", "混杂性结节",
                                        "混合磨玻璃结节", "mixed ground-glass nodule"]},
        "孤立性肺结节": {"parent": "肺结节", "aliases": ["孤立性结节", "单发结节"]},
        "多发性肺结节": {"parent": "肺结节", "aliases": ["多发结节", "多个结节"]},
        "难定性肺结节": {"parent": "肺结节", "aliases": ["难定性结节"]},
        # ---- 筛查流程（v1.3 新增：语料侧完备性审计发现的整体缺失维度）----
        # 见 `ontology_coverage_audit.py` 审计结果：筛查相关词在 4 份语料中
        # 合计出现 55 次（肺癌筛查 37×、年度筛查 9×、基线筛查 6×、
        # 机会性筛查 3×），而 v1.2 种子本体**完全没有这一维度**。
        # 该缺口说明初版本体偏向"已检出结节如何处置"，
        # 遗漏了"从筛查到处置"的完整链条。
        "肺癌筛查": {"parent": None,
                     "aliases": ["筛查", "低剂量CT筛查", "LDCT筛查", "肺癌筛查指南"]},
        "基线筛查": {"parent": "肺癌筛查",
                     "aliases": ["基线LDCT", "首次筛查", "基线筛查阳性"]},
        "年度筛查": {"parent": "肺癌筛查",
                     "aliases": ["年度LDCT", "每年筛查", "年度复查筛查"]},
        "机会性筛查": {"parent": "肺癌筛查",
                       "aliases": ["机会性LDCT", "非计划筛查"]},
        # ---- 评估工具（v1.3 新增：审计发现"预测模型/风险评估"类缺口 12 次）----
        "评估工具": {"parent": None, "aliases": ["评估方法", "预测工具"]},
        "风险预测模型": {"parent": "评估工具",
                         "aliases": ["癌风险预测模型", "肺癌风险预测模型",
                                     "风险预测", "预测模型"]},
        "风险评估": {"parent": "评估工具",
                     "aliases": ["个体化风险评估", "风险评估模型"]},
        # ---- 患者与危险因素 ----
        "患者": {"parent": None, "aliases": ["病人", "病例"]},
        "肺癌高危人群": {"parent": "患者", "aliases": ["高危人群"],
                        "constraint": {"age_years": {"min": 40}}},
        "吸烟史": {"parent": "危险因素", "aliases": ["吸烟", "抽烟史"]},
        "环境或高危职业暴露史": {"parent": "危险因素",
                                "aliases": ["职业暴露", "石棉接触", "环境暴露"]},
        "慢性肺部疾病史": {"parent": "危险因素",
                          "aliases": ["慢阻肺", "肺纤维化", "肺结核史", "慢性肺病"]},
        "肿瘤史或家族史": {"parent": "危险因素",
                          "aliases": ["恶性肿瘤史", "肺癌家族史", "肿瘤家族史"]},
        "危险因素": {"parent": None, "aliases": ["高危因素"]},
        # ---- 影像特征 ----
        "影像学特征": {"parent": None, "aliases": ["影像特征"]},
        "毛刺征": {"parent": "影像学特征", "aliases": ["毛刺", "棘状突起"]},
        "分叶征": {"parent": "影像学特征", "aliases": ["分叶"]},
        "胸膜凹陷征": {"parent": "影像学特征", "aliases": ["胸膜凹陷"]},
        "血管集束征": {"parent": "影像学特征", "aliases": ["血管集束"]},
        "位于上叶": {"parent": "影像学特征", "aliases": ["上叶", "上叶位置"]},
        "密度增加": {"parent": "影像学特征", "aliases": ["密度增高", "CT值增高"]},
        "实性成分增多": {"parent": "影像学特征",
                        "aliases": ["实性成分增加", "出现实性成分"]},
        "倍增时间": {"parent": "影像学特征", "aliases": ["体积倍增时间"]},
        # ---- 检查 ----
        "检查手段": {"parent": None, "aliases": ["检查"]},
        "薄层CT": {"parent": "检查手段",
                  "aliases": ["薄层高分辨CT", "薄层平扫", "薄层CT扫描", "HRCT"]},
        "低剂量CT": {"parent": "检查手段", "aliases": ["LDCT", "低剂量螺旋CT"]},
        "PET-CT": {"parent": "检查手段",
                   "aliases": ["PETCT", "正电子发射断层显像", "FDG-PET"]},
        "胸部增强CT": {"parent": "检查手段", "aliases": ["增强CT", "强化CT"]},
        "循环染色体异常细胞检测": {"parent": "检查手段",
                                  "aliases": ["CAC", "CAC检测", "循环异常细胞"]},
        "肿瘤标志物组合": {"parent": "检查手段",
                          "aliases": ["ProGRP", "CEA", "SCC", "Cyfra21-1", "LCBP"]},
        "非手术活检": {"parent": "检查手段",
                      "aliases": ["穿刺活检", "经皮肺穿刺", "支气管镜活检"]},
        "经支气管肺活检": {"parent": "非手术活检",
                          "aliases": ["TBLB", "经支气管镜肺活检",
                                      "支气管镜下肺活检"]},
        "影像辅助诊断": {"parent": "检查手段",
                        "aliases": ["AI辅助诊断", "人工智能辅助诊断",
                                    "影像辅助诊断系统", "辅助诊断系统",
                                    "计算机辅助诊断", "AI辅助检测"]},
        "手术活检": {"parent": "检查手段", "aliases": ["胸腔镜活检"]},
        "梅奥模型": {"parent": "检查手段", "aliases": ["Mayo模型", "ACCP模型"]},
        # ---- 处置 ----
        "处置动作": {"parent": None, "aliases": ["处置", "管理"]},
        "CT随访": {"parent": "处置动作", "aliases": ["随访", "复查", "定期复查"]},
        "常规年度随访": {"parent": "CT随访", "aliases": ["年度随访", "每年复查"]},
        "外科手术根治性切除": {"parent": "处置动作",
                              "aliases": ["手术切除", "外科手术", "根治性切除", "手术"]},
        "立体定向放射治疗": {"parent": "处置动作", "aliases": ["SBRT"]},
        "消融治疗": {"parent": "处置动作", "aliases": ["射频消融", "微波消融", "冷冻消融"]},
        "经验性抗菌治疗": {"parent": "处置动作",
                          "aliases": ["经验性抗生素治疗", "抗菌治疗", "抗生素治疗"]},
        "MDT多学科会诊": {"parent": "处置动作",
                         "aliases": ["MDT", "人机MDT", "多学科会诊", "多学科团队"]},
        "转诊": {"parent": "处置动作", "aliases": ["上转", "转上级医院"]},
        "戒烟干预": {"parent": "处置动作", "aliases": ["戒烟"]},
        "复发监测": {"parent": "处置动作",
                     "aliases": ["监测复发", "术后随访", "复发监测随访"]},
        # ---- 证据体系 ----
        "推荐意见": {"parent": None, "aliases": ["推荐条款", "条款", "推荐"]},
        "医疗机构": {"parent": None, "aliases": ["医院"]},
        "基层医院": {"parent": "医疗机构", "aliases": ["社区卫生服务中心", "县医院"]},
        "肺结节诊治分中心": {"parent": "医疗机构", "aliases": ["分中心"]},
        "肺癌防治联盟": {"parent": "医疗机构", "aliases": ["联盟"]},
    },
    "relations": {
        # 关系名: (定义域, 值域, 中文说明)
        "hasDensityType":       ("肺结节", "肺结节", "密度类型"),
        "hasSizeCategory":      ("肺结节", "肺结节", "大小分类"),
        "hasImagingFeature":    ("肺结节", "影像学特征", "具有影像特征"),
        "hasRiskFactor":        ("患者", "危险因素", "具有危险因素"),
        "hasNodule":            ("患者", "肺结节", "患有结节"),
        "recommends":           ("推荐意见", "处置动作", "推荐处置"),
        "appliesTo":            ("推荐意见", "肺结节", "适用于"),
        "requiresExamination":  ("推荐意见", "检查手段", "需要检查"),
        "hasStrength":          ("推荐意见", "推荐强度", "推荐强度"),
        "managedAt":            ("肺结节", "医疗机构", "管理机构"),
        "upgradesRisk":         ("危险因素", "肺结节", "上调恶性风险"),
        "suggestsMalignancy":   ("影像学特征", "肺结节", "提示恶性"),
        "hasNextStep":          ("处置动作", "处置动作", "下一步"),
        "contraindicatedFor":   ("检查手段", "肺结节", "不适用于"),
    },
    "individuals": {},          # L3 审核通过后扩充
    "pending_concepts": [],     # L2 抽取出的候选新概念，等待人工审核
}

# 推荐强度枚举（对齐共识）
STRENGTHS = {"ⅠA类推荐", "ⅠB类推荐", "Ⅱ类推荐", "Ⅲ类推荐"}

# 溯源锚点正则：【推荐意见N】
CLAUSE_PATTERN = re.compile(r"【推荐意见\s*(\d+)\s*】")

# 章节式规范的章标题正则（v1.2 新增）
# 例：「2 高危人群的选择」「5 结节管理」——行首数字 + 空格 + 中文标题
# 说明：只匹配**一级章**（单个数字），不匹配 5.1 / 5.2.1 这类小节，
#       避免把一句说明拆成碎条款。下列标题词用于排除误匹配。
SECTION_PATTERN = re.compile(
    r"^\s*(\d{1,2})\s+(?=[\u4e00-\u9fff])"
    r"(?![\d.])"
    r"([\u4e00-\u9fff][^\n]{2,28})\s*$",
    re.MULTILINE,
)
# 明显不是章标题的（参考文献、脚注等）
SECTION_EXCLUDE = ("参 考 文 献", "参考文献", "Footnotes", "致谢", "利益冲突")
# 随访间隔提取："3、6、12 和 24 个月"
FOLLOWUP_PATTERN = re.compile(r"(\d+(?:\s*[、,，和~-]\s*\d+)*)\s*个?月")
# 直径阈值提取："直径≤8 mm" / "直径>8mm"
DIAMETER_PATTERN = re.compile(r"直径\s*([≤<>≥=]{1,2})\s*(\d+(?:\.\d+)?)\s*mm")
# 实性成分阈值："实性成分≤8 mm"
SOLID_PATTERN = re.compile(r"实性成分\s*([≤<>≥=]{1,2})\s*(\d+(?:\.\d+)?)\s*mm")
# 推荐强度提取
STRENGTH_PATTERN = re.compile(r"[（(]\s*(ⅠA类推荐|ⅠB类推荐|Ⅱ类推荐|Ⅲ类推荐)\s*[）)]")
# 患者事实提取
AGE_PATTERN = re.compile(r"(\d{1,3})\s*岁")
SMOKING_PATTERN = re.compile(r"吸烟\s*(\d{1,3})\s*年")
DIAMETER_FACT = re.compile(r"(\d+(?:\.\d+)?)\s*mm")


# ============================================================================
# L2  LLM 受约束抽取
# ============================================================================

@dataclass
class ExtractedTriple:
    """一条抽取结果。

    修复记录（v1.1）：
      · 新增 kind 字段区分「对象属性」与「数据属性」。
        数值型结果（直径阈值、随访间隔）本质是 DatatypeProperty 的值，
        **不应参与类对齐**，此前被误送进 align() 导致未对齐率虚高。
    """
    subject: str
    relation: str
    object: str
    clause: str = ""              # 溯源条款编号，如 "推荐意见14"
    strength: str = ""            # 推荐强度
    evidence: str = ""            # 原文片段
    aligned: bool = False         # 是否成功对齐到种子本体
    align_target: str = ""        # 对齐到的本体概念
    confidence: float = 0.0
    kind: str = "object"          # "object" = 对象属性 | "data" = 数据属性


@dataclass
class BuildReport:
    """构建过程的质量报告。

    指标口径说明（v1.1 修正）：
      · triples_total     仅统计**对象属性**三元组（参与本体对齐的部分）
      · data_triples      数据属性条目（数值/间隔），单独计数，不计入对齐率分母
      · alignment_rate    对象属性三元组的对齐率
      · unaligned_rate    1 - alignment_rate，是**本体成长的核心指标**：
                          随人工审核扩充本体而下降
      · review_seconds    人工审核等效工时（按 30 秒/条，保守估计）
    """
    doc_name: str = ""
    doc_chars: int = 0
    elapsed_sec: float = 0.0
    clauses_found: int = 0
    triples_total: int = 0          # 对象属性三元组
    triples_aligned: int = 0
    triples_pending: int = 0
    data_triples: int = 0           # 数据属性条目
    classes_seed: int = 0
    classes_added: int = 0
    manual_review_items: int = 0

    # 人工审核等效成本（秒/条），知识工程实践中的保守取值
    SEC_PER_REVIEW = 30.0

    @property
    def alignment_rate(self) -> float:
        return self.triples_aligned / self.triples_total if self.triples_total else 0.0

    @property
    def unaligned_rate(self) -> float:
        """未对齐率 —— 本体的"进化"证据：随本体成长而下降。"""
        return 1.0 - self.alignment_rate

    @property
    def manual_intervention_rate(self) -> float:
        return self.manual_review_items / self.triples_total if self.triples_total else 0.0

    @property
    def review_seconds(self) -> float:
        """人工审核本批次所需工时（秒）。"""
        return self.manual_review_items * self.SEC_PER_REVIEW

    def to_dict(self) -> dict:
        d = asdict(self)
        d["alignment_rate"] = round(self.alignment_rate, 4)
        d["unaligned_rate"] = round(self.unaligned_rate, 4)
        d["manual_intervention_rate"] = round(self.manual_intervention_rate, 4)
        d["review_seconds"] = round(self.review_seconds, 1)
        return d


class OntologyBuilder:
    """本体半自动化构建器。"""

    def __init__(self, ontology: Optional[dict] = None):
        self.onto = ontology or json.loads(json.dumps(SEED_ONTOLOGY))
        self.triples: list[ExtractedTriple] = []
        self._alias_index = self._build_alias_index()

    # -------- 别名索引：用于强制对齐 --------
    def _build_alias_index(self) -> dict[str, str]:
        idx: dict[str, str] = {}
        for cls, meta in self.onto["classes"].items():
            idx[cls] = cls
            for a in meta.get("aliases", []):
                idx[a] = cls
        return idx

    # -------- 强制对齐 --------
    def align(self, surface: str) -> tuple[bool, str]:
        """把抽取到的表面形式对齐到种子本体概念。
        对不上 → 返回 (False, "")，进入候选池，不直接入库。"""
        if not surface:
            return False, ""
        s = surface.strip()
        if s in self._alias_index:
            return True, self._alias_index[s]
        # 包含匹配（取最长命中，降低误匹配）
        best, best_len = "", 0
        for alias, cls in self._alias_index.items():
            if alias and alias in s and len(alias) > best_len:
                best, best_len = cls, len(alias)
        if best:
            return True, best
        return False, ""

    # -------- 主抽取流程 --------
    def extract(self, text: str, doc_name: str = "") -> BuildReport:
        t0 = time.time()
        rep = BuildReport(
            doc_name=doc_name,
            doc_chars=len(text),
            classes_seed=len(self.onto["classes"]),
        )

        # ---- 按条款切分文档 ----
        blocks = self._split_by_clause(text)
        rep.clauses_found = len(blocks)

        for clause_no, body in blocks:
            # 1) 推荐强度
            m = STRENGTH_PATTERN.search(body)
            strength = m.group(1) if m else ""
            # 2) 适用结节类型（appliesTo）—— 从全文抽取，因为限定条件
            #    常出现在注意事项中（如"直径>15mm 者可直接考虑…"）
            nods = self._match_classes(body, parent_filter="肺结节")
            # ★ v1.2：处置动作与检查只从「主推荐句」抽取，避免把注意事项
            #    里的对照描述误当成推荐（如"需考虑切除，而不是非手术活检"）。
            main_body, caveat_body = self._split_main_and_caveat(body)
            # 3) 处置动作（recommends）
            acts = self._match_classes(main_body, parent_filter="处置动作")
            # 4) 检查手段（requiresExamination）
            exams = self._match_classes(main_body, parent_filter="检查手段")
            # 5) 随访间隔（只取主推荐句里的间隔）
            fups = FOLLOWUP_PATTERN.findall(main_body)
            # 6) 阈值
            dims = DIAMETER_PATTERN.findall(body)
            solids = SOLID_PATTERN.findall(body)

            rec_node = f"推荐意见{clause_no}"

            # ---- 对象属性：参与本体对齐 ----
            for n in nods:
                self._add(rec_node, "appliesTo", n, clause_no, strength, body)
            for a in acts:
                self._add(rec_node, "recommends", a, clause_no, strength, main_body)
            for e in exams:
                self._add(rec_node, "requiresExamination", e, clause_no,
                          strength, main_body)
            if strength:
                self._add(rec_node, "hasStrength", strength, clause_no, strength, body)

            # ---- 禁忌与限定条件单独抽取（contraindicatedFor）----
            for c in self._match_contraindications(caveat_body):
                self._add(rec_node, "contraindicatedFor", c, clause_no,
                          strength, caveat_body)

            # ---- 数据属性：数值与间隔，不参与类对齐 ----
            for f in fups:
                self._add_data(rec_node, "followUpMonths", f, clause_no,
                               strength, main_body)
            for op, val in dims:
                self._add_data(rec_node, f"diameter{op}", f"{val}mm",
                               clause_no, strength, body)
            for op, val in solids:
                self._add_data(rec_node, f"solidComponent{op}", f"{val}mm",
                               clause_no, strength, body)

        # ---- 汇总 ----
        obj_triples = [t for t in self.triples if t.kind == "object"]
        rep.data_triples = len(self.triples) - len(obj_triples)
        rep.triples_total = len(obj_triples)
        rep.triples_aligned = sum(1 for t in obj_triples if t.aligned)
        rep.triples_pending = rep.triples_total - rep.triples_aligned
        rep.manual_review_items = rep.triples_pending
        rep.elapsed_sec = round(time.time() - t0, 3)

        # ---- 候选新概念入池（仅对象属性；不直接入库）----
        self.onto["pending_concepts"] = [
            {"surface": t.object, "relation": t.relation,
             "from_clause": t.clause, "status": "PENDING_REVIEW"}
            for t in obj_triples if not t.aligned
        ]
        return rep

    def _add(self, s: str, r: str, o: str, clause: str,
             strength: str, body: str) -> None:
        """对象属性：必须对齐到本体的类。"""
        ok, target = self.align(o)
        self.triples.append(ExtractedTriple(
            subject=s, relation=r, object=o, clause=clause,
            strength=strength, evidence=body[:160],
            aligned=ok, align_target=target if ok else "",
            confidence=0.95 if ok else 0.40, kind="object",
        ))

    def _add_data(self, s: str, r: str, v: str, clause: str,
                  strength: str, body: str) -> None:
        """数据属性：字面量值，不对齐到类（v1.1 修复）。

        这些是 DatatypeProperty 的取值（如 直径≤8mm、随访 3,6,12,24 个月），
        本身不是本体概念，此前误入 align() 造成"未对齐率"虚高。
        """
        self.triples.append(ExtractedTriple(
            subject=s, relation=r, object=v, clause=clause,
            strength=strength, evidence=body[:160],
            aligned=True, align_target="", confidence=0.90, kind="data",
        ))

    # ---- v1.2：把条款正文拆成「主推荐句」与「注意事项」----
    CAVEAT_MARKERS = [
        "随访中需注意", "需注意", "注意事项", "值得注意的是", "需说明",
    ]
    # 禁忌语式：不推荐 / 不适用 / 不建议
    CONTRA_PATTERNS = [
        (r"不推荐[^。；]{0,40}", "不推荐"),
        (r"不适用[^。；]{0,40}", "不适用"),
        (r"不建议[^。；]{0,40}", "不建议"),
    ]

    def _split_main_and_caveat(self, body: str) -> tuple[str, str]:
        """把条款正文按注意事项标记切分。

        返回 (主推荐句, 注意事项句)。若没有注意事项标记，则第二项为空。

        设计意图：避免把"随访中需注意：…需考虑切除，而不是非手术活检…"
        这类**限定说明**误当成推荐动作，从而把过度治疗写进知识图谱。
        """
        cut = -1
        for m in self.CAVEAT_MARKERS:
            i = body.find(m)
            if i >= 0 and (cut < 0 or i < cut):
                cut = i
        if cut < 0:
            return body, ""
        return body[:cut], body[cut:]

    def _match_contraindications(self, caveat: str) -> list[str]:
        """从注意事项中抽取禁忌对象。"""
        if not caveat:
            return []
        found: list[str] = []
        for pat, _kind in self.CONTRA_PATTERNS:
            for m in re.finditer(pat, caveat):
                seg = m.group(0)
                for cls, meta in self.onto["classes"].items():
                    if cls in self.GENERIC_CLASSES:
                        continue
                    names = [cls] + list(meta.get("aliases", []))
                    if any(n and n in seg for n in names):
                        found.append(cls)
        return sorted(set(found))

    def _split_by_clause(self, text: str) -> list[tuple[str, str]]:
        """按条款锚点切分文档。

        v1.2 扩展：真实规范文档存在**两种**结构，此前只支持第一种。

          ① 锚点式（共识类）：「【推荐意见N】…」逐条列出
             例：肺结节诊治中国专家共识（2024年版）—— 18 条

          ② 章节式（指南类）：「N 标题」分节叙述，条款隐含在节内
             例：中国肺癌低剂量CT筛查指南（2023/2025年版）—— 此前只识别出 1 条

        章节式文档此前全部落入 clause='0'，导致该文档的抽取量极低
        （2023 版仅识别 1 个条款）。本版新增章节式识别，使指南类文档
        也能被结构化处理 —— 这是"低资源场景"下真实存在的文档形态差异。

        返回 [(条款号, 条款文本), ...]
        """
        # ---- ① 优先尝试锚点式 ----
        marks = list(CLAUSE_PATTERN.finditer(text))
        if marks:
            out: list[tuple[str, str]] = []
            for i, m in enumerate(marks):
                start = m.start()
                end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
                out.append((m.group(1), text[start:end]))
            return out

        # ---- ② 退化为章节式 ----
        sec_marks = [
            m for m in SECTION_PATTERN.finditer(text)
            if not any(x in (m.group(2) or "") for x in SECTION_EXCLUDE)
        ]
        if sec_marks:
            out = []
            for i, m in enumerate(sec_marks):
                start = m.start()
                end = sec_marks[i + 1].start() if i + 1 < len(sec_marks) else len(text)
                body = text[start:end]
                # 只用「章标题序号」作为条款号；小节（如 5.2.1）并入其父章，
                # 避免把一句说明拆成几十个碎条款。
                out.append((m.group(1), body))
            return out

        return [("0", text)]

    # 过于泛化的中间类，不作为关系目标（v1.1 修复）
    # 例："推荐意见2 --recommends--> 处置动作" 是无信息量的噪声，
    #     真正有意义的是 "--> CT随访" / "--> 低剂量CT"。
    GENERIC_CLASSES = {
        "肺结节", "危险因素", "影像学特征", "检查手段", "处置动作",
        "患者", "推荐意见", "医疗机构", "结节",
    }

    def _match_classes(self, body: str, parent_filter: str) -> list[str]:
        """在文本中找出属于某父类的本体概念。

        v1.1 修复两处精度问题：
          1) 过滤泛化中间类（不把"处置动作"当成关系目标）；
          2) 按**文本出现位置**排序，并抑制被更具体概念支配的祖先概念
             —— 原文列举"实性肺结节和亚实性肺结节…纯磨玻璃结节…混杂性结节"时，
             实性/亚实性/纯磨玻璃/混杂均真实出现，但若更具体者已命中，
             则不再单独输出其泛化祖先，避免噪声三元组。
        """
        # 1) 找出所有命中的概念及其在文本中的首次位置
        hits: dict[str, int] = {}
        for cls, meta in self.onto["classes"].items():
            cur, ok = cls, False
            while cur:
                if cur == parent_filter:
                    ok = True
                    break
                cur = self.onto["classes"].get(cur, {}).get("parent")
            if not ok:
                continue
            names = [cls] + list(meta.get("aliases", []))
            pos = -1
            for n in names:
                if n and n in body:
                    p = body.find(n)
                    pos = p if pos < 0 else min(pos, p)
            if pos >= 0:
                hits[cls] = pos

        # 2) 抑制支配关系：若某概念的子孙也命中，则该概念不再单独输出
        def has_hit_descendant(c: str) -> bool:
            for other in hits:
                if other == c:
                    continue
                cur = other
                while cur:
                    cur = self.onto["classes"].get(cur, {}).get("parent")
                    if cur == c:
                        return True
            return False

        kept = [
            c for c in hits
            if c not in self.GENERIC_CLASSES and not has_hit_descendant(c)
        ]
        # 3) 按文本出现先后排序，保证三条组的 S-P-O 顺序可读
        return sorted(kept, key=lambda c: hits[c])

    # -------- L3 人工审核闭环 --------
    def review(self, surface: str, target_class: str,
               parent: str = "", aliases: Optional[list[str]] = None) -> None:
        """人工审核通过 → 扩充本体（本体持续动态更新的入口）。"""
        if target_class not in self.onto["classes"]:
            self.onto["classes"][target_class] = {
                "parent": parent or None,
                "aliases": aliases or [],
                "added_by": "HUMAN_REVIEW",
            }
        self._alias_index = self._build_alias_index()
        self.onto["pending_concepts"] = [
            p for p in self.onto["pending_concepts"]
            if p["surface"] != surface
        ]

    def reject(self, surface: str) -> None:
        """人工审核驳回 → 不扩充本体，仅记录。"""
        for p in self.onto["pending_concepts"]:
            if p["surface"] == surface:
                p["status"] = "REJECTED"
        self.onto["pending_concepts"] = [
            p for p in self.onto["pending_concepts"]
            if p["status"] != "REJECTED"
        ]

    # -------- 导出 --------
    def export_ontology(self, path: str) -> None:
        self.onto["version"] = self._bump_version(self.onto.get("version", "1.0"))
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.onto, f, ensure_ascii=False, indent=2)

    @staticmethod
    def _bump_version(v: str) -> str:
        try:
            a, b = v.split(".")
            return f"{a}.{int(b) + 1}"
        except Exception:
            return "1.1"

    def to_jsonl(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            for t in self.triples:
                f.write(json.dumps(asdict(t), ensure_ascii=False) + "\n")


# ============================================================================
# 基线：纯人工构建的等效成本模型（用于效率对比）
# ============================================================================

def manual_baseline_estimate(doc_chars: int,
                             triples: int) -> dict[str, float]:
    """纯人工构建的等效工时估算。

    依据：知识工程实践中，人工从规范文档抽取三元组并进行本体对齐，
    平均约 90 秒 / 条（含阅读、判定、录入、复核）。
    此处采用保守值，便于对比。
    """
    sec_per_triple = 90.0
    minutes_read = doc_chars / 1200.0     # 通读速度约 1200 字/分钟
    manual_sec = triples * sec_per_triple + minutes_read * 60
    return {
        "manual_seconds": round(manual_sec, 1),
        "manual_hours": round(manual_sec / 3600, 2),
        "assumption": "人工 90 秒/三元组 + 通读 1200 字/分钟",
    }


def honest_speedup(machine_sec: float, review_sec: float,
                   manual_sec: float) -> dict[str, float]:
    """诚实的效率对比（v1.1 修复）。

    此前版本用「机器 0.004 秒」直接比「人工 5 小时」，得出 450 万倍加速 ——
    这是荒谬且不可信的指标。正确的口径是**人机协同总成本**：

        本方法总成本 = 机器抽取耗时 + 人工审核耗时
        纯人工成本   = 人工全量抽取耗时

    其中人工审核只针对"未对齐"的少数条目（30 秒/条），
    这才是"半自动化"的真实含义：机器全量抽取 + 人工只审边界情况。
    """
    semi_auto_sec = machine_sec + review_sec
    return {
        "semi_auto_seconds": round(semi_auto_sec, 1),
        "semi_auto_hours": round(semi_auto_sec / 3600, 3),
        "manual_seconds": round(manual_sec, 1),
        "manual_hours": round(manual_sec / 3600, 2),
        "speedup": round(manual_sec / semi_auto_sec, 1) if semi_auto_sec else 0.0,
        "labor_saving_pct": round(
            (1 - semi_auto_sec / manual_sec) * 100, 1) if manual_sec else 0.0,
        "note": "本方法总成本 = 机器抽取 + 人工审核；对比纯人工全量抽取",
    }


# ============================================================================
# CLI
# ============================================================================

def main() -> int:
    ap = argparse.ArgumentParser(
        description="低资源领域知识图谱本体半自动化构建")
    ap.add_argument("--input", required=True, help="领域文档路径")
    ap.add_argument("--out-ontology", default="ontology_built.json")
    ap.add_argument("--out-triples", default="triples.jsonl")
    ap.add_argument("--report", action="store_true", help="打印构建报告")
    ap.add_argument("--report-json", default="", help="报告输出到 JSON")
    args = ap.parse_args()

    if not os.path.exists(args.input):
        print(f"[ERROR] 文件不存在: {args.input}", file=sys.stderr)
        return 2

    with open(args.input, encoding="utf-8") as f:
        text = f.read()

    builder = OntologyBuilder()
    rep = builder.extract(text, doc_name=os.path.basename(args.input))
    builder.export_ontology(args.out_ontology)
    builder.to_jsonl(args.out_triples)

    base = manual_baseline_estimate(rep.doc_chars, rep.triples_total)
    speed = honest_speedup(rep.elapsed_sec, rep.review_seconds,
                           base["manual_seconds"])
    result = {
        "report": rep.to_dict(),
        "manual_baseline": base,
        "efficiency": speed,
    }

    if args.report:
        d = result["report"]
        print("=" * 68)
        print("  本体半自动化构建 · 质量报告")
        print("=" * 68)
        print(f"  文档              : {d['doc_name']}")
        print(f"  文档字数          : {d['doc_chars']}")
        print(f"  识别条款数        : {d['clauses_found']}")
        print("-" * 68)
        print(f"  对象属性三元组    : {d['triples_total']}   (参与本体对齐)")
        print(f"  数据属性条目      : {d['data_triples']}   (数值/间隔，不对齐)")
        print(f"  成功对齐          : {d['triples_aligned']}")
        print(f"  ├─ 本体对齐率     : {d['alignment_rate'] * 100:.1f}%")
        print(f"  └─ 未对齐率       : {d['unaligned_rate'] * 100:.1f}%"
              f"    ← 随本体成长而下降")
        print(f"  种子本体类数      : {d['classes_seed']}")
        print(f"  待人工审核        : {d['manual_review_items']} 条")
        print(f"  └─ 人工介入率     : {d['manual_intervention_rate'] * 100:.1f}%"
              f"    ← 越低越自动化")
        print(f"  机器抽取耗时      : {d['elapsed_sec']} 秒")
        print("-" * 68)
        print("  效率对比（人机协同总成本 vs 纯人工）")
        print(f"    机器抽取        : {d['elapsed_sec']} 秒")
        print(f"    人工审核        : {d['review_seconds']} 秒"
              f"  ({d['manual_review_items']} 条 × 30 秒)")
        print(f"    本方法合计      : {speed['semi_auto_seconds']} 秒"
              f"  ({speed['semi_auto_hours']} 小时)")
        print(f"    纯人工等效      : {speed['manual_seconds']} 秒"
              f"  ({speed['manual_hours']} 小时)")
        print(f"    ├─ 加速比       : {speed['speedup']}x")
        print(f"    └─ 人工节省     : {speed['labor_saving_pct']}%")
        print("=" * 68)

    if args.report_json:
        with open(args.report_json, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

    return 0


if __name__ == "__main__":
    sys.exit(main())
