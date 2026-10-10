#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
领域数据资产标识（Asset Identification）模块
================================================================

对应赛题要求：
  "实现对文本、表格、图文等多元行业数据的统一识别、理解与资产标识。"

设计目标
----------------------------------------------------------------
  为每一份入库的领域数据资产建立**统一元数据画像**，使数据可被：
    · 统一识别 —— 无论来源格式，都有相同的标识结构
    · 统一理解 —— 通过语义标签与知识挂载点接入知识图谱
    · 可治理   —— 可信度、时效性、合规等级可审计

标识维度（六维）
----------------------------------------------------------------
  1. 来源标识  provenance   —— 谁发布的、什么级别的权威
  2. 类型标识  modality     —— 文本 / 表格 / 图文
  3. 时效标识  temporal     —— 发布时间、有效期、指南版本
  4. 关联标识  linkage      —— 挂载到本体的哪些概念、覆盖哪些条款
  5. 可信标识  trust        —— 证据等级、同行评议状态、推荐强度分布
  6. 治理标识  governance   —— 版权、合规等级、可外发范围

用法：
    python3 asset_identifier.py --assets assets.json --report
    python3 asset_identifier.py --scan /path/to/docs --out assets.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass, field, asdict
from datetime import date
from typing import Any, Optional


# ============================================================================
# 一、受控词表（保证标识的一致性，避免自由文本）
# ============================================================================

MODALITY = {
    "text":   "文本",
    "table":  "表格",
    "image":  "图文",
    "mixed":  "混合",
}

# 来源权威等级
AUTHORITY_LEVEL = {
    "L1": "国家/国际学术组织发布的指南或共识",
    "L2": "国家级学会/协会发布的专家共识",
    "L3": "省级学会或行业团体规范",
    "L4": "医疗机构内部规范或 SOP",
    "L5": "个人经验总结或非正式资料",
}

# 证据等级（参照 GRADE 与共识推荐强度体系）
EVIDENCE_LEVEL = {
    "IA": "ⅠA类推荐（强推荐，高质量证据）",
    "IB": "ⅠB类推荐（强推荐，中等质量证据）",
    "II": "Ⅱ类推荐（弱推荐）",
    "III": "Ⅲ类推荐（专家意见为主）",
    "NA": "未分级",
}

# 合规等级
COMPLIANCE = {
    "PUBLIC":   "完全公开，可自由分发",
    "CITE":     "公开但需标注出处",
    "INTERNAL": "机构内部使用，不得外发",
    "RESTRICTED": "含敏感信息，受限访问",
}

# 时效状态
FRESHNESS = {
    "CURRENT":  "现行有效",
    "SUPERSEDED": "已被新版取代",
    "DRAFT":    "征求意见稿",
    "UNKNOWN":  "无法判定",
}


# ============================================================================
# 二、资产标识数据结构
# ============================================================================

@dataclass
class AssetIdentifier:
    """一份领域数据资产的六维标识。"""

    # ---- 基本信息 ----
    asset_id: str = ""              # 稳定标识（基于内容哈希）
    asset_name: str = ""
    modality: str = "text"          # text / table / image / mixed
    file_format: str = ""           # pdf / docx / txt / png ...
    size_bytes: int = 0
    content_hash: str = ""          # SHA-256 前 16 位

    # ---- 1. 来源标识 ----
    publisher: str = ""
    authority_level: str = "L2"
    citation: str = ""
    source_url: str = ""

    # ---- 2. 类型标识 ----
    structure_type: str = ""        # 章节化散文 / 结构化表格 / 影像报告
    has_tables: bool = False
    has_images: bool = False
    language: str = "zh"

    # ---- 3. 时效标识 ----
    publish_date: str = ""
    version: str = ""
    freshness: str = "CURRENT"

    # ---- 4. 关联标识（与知识图谱的挂载点）----
    concepts: list[str] = field(default_factory=list)
    clauses: list[str] = field(default_factory=list)
    kg_node_refs: list[str] = field(default_factory=list)

    # ---- 5. 可信标识 ----
    evidence_level: str = "III"
    strength_distribution: dict[str, int] = field(default_factory=dict)
    peer_reviewed: bool = True
    retrievable: bool = True        # 是否已通过本体对齐验证

    # ---- 6. 治理标识 ----
    compliance: str = "CITE"
    copyright_holder: str = ""
    redistribution: str = ""
    contains_patient_data: bool = False

    # ---- 处理状态 ----
    status: str = "REGISTERED"      # REGISTERED / INDEXED / ALIGNED
    processed_by: str = "ontology_builder"
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ============================================================================
# 三、标识生成器
# ============================================================================

class AssetRegistry:
    """资产标识注册表。"""

    def __init__(self) -> None:
        self.assets: dict[str, AssetIdentifier] = {}

    # ---- 从文件扫描生成标识 ----
    def register_file(self, path: str, **overrides: Any) -> AssetIdentifier:
        name = os.path.basename(path)
        ext = os.path.splitext(name)[1].lstrip(".").lower()
        with open(path, "rb") as f:
            raw = f.read()
        h = hashlib.sha256(raw).hexdigest()[:16]

        # 文本类文件读取内容，用于语义分析
        text = ""
        if ext in ("txt", "md", "csv"):
            try:
                text = raw.decode("utf-8", "replace")
            except Exception:
                text = ""

        aid = AssetIdentifier(
            asset_id=f"AST-{h[:8].upper()}",
            asset_name=name,
            file_format=ext,
            size_bytes=len(raw),
            content_hash=h,
            modality=self._infer_modality(ext, text),
            structure_type=self._infer_structure(ext, text),
            has_tables=self._detect_tables(text),
            has_images=self._detect_image_ref(text),
        )

        # 语义分析：概念与条款挂载
        if text:
            aid.concepts = self._extract_concepts(text)
            aid.clauses = self._extract_clauses(text)
            aid.strength_distribution = self._strength_distribution(text)
            aid.evidence_level = self._infer_evidence_level(
                aid.strength_distribution)

        # 应用人工覆盖（来源、合规等无法自动判定的字段）
        for k, v in overrides.items():
            if hasattr(aid, k):
                setattr(aid, k, v)

        aid.kg_node_refs = [f"pno:{c}" for c in aid.concepts[:20]]
        self.assets[aid.asset_id] = aid
        return aid

    # ---- 推断方法 ----
    @staticmethod
    def _infer_modality(ext: str, text: str) -> str:
        """推断数据模态。

        v1.1 增强：除扩展名外增加**内容语义探测**。
        纯文本文件若内容为影像/结构化报告形态，应标识为"图文"模态，
        否则"图文"类资产会被误判为普通文本，导致多模态覆盖度被低估。
        """
        if ext in ("png", "jpg", "jpeg", "webp", "gif", "bmp", "tiff", "dcm"):
            return "image"
        if ext in ("csv", "xlsx", "xls"):
            return "table"
        if ext in ("docx", "doc"):
            return "mixed" if AssetRegistry._detect_tables(text) else "text"
        if ext == "pdf":
            return "mixed"
        # ---- 内容语义探测（针对纯文本文件）----
        if text and AssetRegistry._looks_like_imaging_report(text):
            return "image"
        if text and AssetRegistry._detect_tables(text):
            return "table"
        return "text"

    @staticmethod
    def _looks_like_imaging_report(text: str) -> bool:
        """判断文本是否为**报告形态**（而非论述指南）。

        v1.2 收紧判据：v1.1 仅凭关键词出现次数判断，导致论述性指南
        （正文中同样含"密度类型""实性成分"等词）被误判为影像报告。

        报告形态的特征是**字段名后紧跟冒号与取值**，例如：
            最大径    ：8 mm
            密度类型  ：混杂性磨玻璃结节（mGGN）
        而论述性文本中这些词出现在句子里，不构成字段结构。

        因此判据改为：字段名 + 分隔符（全/半角冒号）+ 内容的**配对**数量。
        """
        # 报告字段名（要求后接冒号才计数）
        field_names = [
            "最大径", "密度类型", "实性成分", "边缘", "分叶",
            "胸膜凹陷", "血管集束", "钙化", "既往对比", "位置",
            "检查项目", "报告类型", "影像学印象", "影像所见",
        ]
        paired = 0
        for fn in field_names:
            # 字段名后可跟空白/全角空格，然后是冒号（全角或半角）
            if re.search(re.escape(fn) + r"[\s\u3000]*[:：]", text):
                paired += 1
        # 报告术语（这些词在论述性指南中基本不出现）
        report_markers = ["影像学印象", "影像所见", "报告医师", "结构化报告"]
        markers = sum(1 for k in report_markers if k in text)
        # 需同时具备"字段配对结构"与"报告术语"才判定为报告
        return (paired >= 4 and markers >= 1)

    @staticmethod
    def _infer_structure(ext: str, text: str) -> str:
        if ext in ("png", "jpg", "jpeg", "webp"):
            return "图像"
        if ext in ("csv", "xlsx"):
            return "结构化表格"
        if re.search(r"【推荐意见\d+】", text):
            return "条款化指南文本"
        if re.search(r"(?m)^#{1,3}\s", text):
            return "章节化文档"
        return "自由文本"

    @staticmethod
    def _detect_tables(text: str) -> bool:
        # Markdown 表格 或 制表符/多空格对齐的表格
        return bool(re.search(r"(?m)^\s*\|.+\|\s*$", text))

    @staticmethod
    def _detect_image_ref(text: str) -> bool:
        return bool(re.search(r"!\[|<img|\.png|\.jpg|DICOM|影像", text))

    @staticmethod
    def _extract_concepts(text: str) -> list[str]:
        """提取文本中出现的本体概念（用于建立资产与图谱的挂载关系）。"""
        VOCAB = [
            "肺结节", "微小结节", "小结节", "较大结节",
            "实性肺结节", "亚实性肺结节", "纯磨玻璃结节", "混杂性磨玻璃结节",
            "孤立性肺结节", "多发性肺结节", "难定性肺结节",
            "肺癌高危人群", "吸烟史", "环境或高危职业暴露史",
            "慢性肺部疾病史", "肿瘤史或家族史",
            "毛刺征", "分叶征", "胸膜凹陷征", "血管集束征", "位于上叶",
            "密度增加", "实性成分增多", "倍增时间",
            "薄层CT", "低剂量CT", "PET-CT", "胸部增强CT",
            "循环染色体异常细胞检测", "肿瘤标志物组合", "非手术活检", "手术活检",
            "CT随访", "常规年度随访", "外科手术根治性切除",
            "立体定向放射治疗", "消融治疗", "经验性抗菌治疗",
            "MDT多学科会诊", "转诊", "戒烟干预",
            "基层医院", "肺结节诊治分中心", "肺癌防治联盟",
        ]
        found = []
        for v in VOCAB:
            if v in text:
                found.append(v)
        # 别名归一
        if "mGGN" in text and "混杂性磨玻璃结节" not in found:
            found.append("混杂性磨玻璃结节")
        if "pGGN" in text and "纯磨玻璃结节" not in found:
            found.append("纯磨玻璃结节")
        return found

    @staticmethod
    def _extract_clauses(text: str) -> list[str]:
        """提取资产覆盖的条款编号。

        支持两种格式：
          1. 散文条款锚点：【推荐意见14】
          2. 结构化表格列值：条款编号,推荐意见14,... （CSV 首列）
        """
        nums = {int(m) for m in re.findall(r"【推荐意见\s*(\d+)\s*】", text)}
        # CSV 形态：行首为 "推荐意见N"
        for m in re.finditer(r"(?m)^推荐意见(\d+)\s*,", text):
            nums.add(int(m.group(1)))
        # Markdown 表格形态：| 推荐意见N |
        for m in re.finditer(r"\|\s*推荐意见(\d+)\s*\|", text):
            nums.add(int(m.group(1)))
        return [f"推荐意见{n}" for n in sorted(nums)]

    @staticmethod
    def _strength_distribution(text: str) -> dict[str, int]:
        d: dict[str, int] = {}
        for m in re.finditer(r"[（(]\s*(ⅠA类推荐|ⅠB类推荐|Ⅱ类推荐|Ⅲ类推荐)\s*[）)]", text):
            k = m.group(1)
            d[k] = d.get(k, 0) + 1
        return d

    @staticmethod
    def _infer_evidence_level(dist: dict[str, int]) -> str:
        if not dist:
            return "NA"
        # 取分布中最强的等级作为资产整体证据等级
        for lv in ("ⅠA类推荐", "ⅠB类推荐", "Ⅱ类推荐", "Ⅲ类推荐"):
            if dist.get(lv):
                return {"ⅠA类推荐": "IA", "ⅠB类推荐": "IB",
                        "Ⅱ类推荐": "II", "Ⅲ类推荐": "III"}[lv]
        return "NA"

    def to_json(self, path: str) -> None:
        payload = {
            "schema_version": "1.0",
            "generated_at": date.today().isoformat(),
            "controlled_vocabularies": {
                "modality": MODALITY,
                "authority_level": AUTHORITY_LEVEL,
                "evidence_level": EVIDENCE_LEVEL,
                "compliance": COMPLIANCE,
                "freshness": FRESHNESS,
            },
            "asset_count": len(self.assets),
            "assets": [a.to_dict() for a in self.assets.values()],
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)


# ============================================================================
# 四、预置资产清单（本项目的 3 份真实文档）
# ============================================================================

PRESET_ASSETS = [
    {
        "file": "肺结节诊治中国专家共识2024年版_全文.txt",
        "publisher": "中华医学会呼吸病学分会 / 中国肺癌防治联盟专家组",
        "authority_level": "L1",
        "citation": "中华结核和呼吸杂志, 2024, 47(8): 716-729. "
                    "DOI: 10.3760/cma.j.cn112147-20231109-00300",
        "source_url": "https://www.rccrc.cn/article/1820",
        "publish_date": "2024-08-30",
        "version": "2024年版（第三次修订）",
        "compliance": "CITE",
        "copyright_holder": "中华医学会呼吸病学分会",
        "redistribution": "可引用，需标注完整出处",
        "peer_reviewed": True,
    },
    {
        "file": "共识2025_全文.txt",
        "publisher": "中国健康管理协会等",
        "authority_level": "L2",
        "citation": "肺癌筛查及肺结节健康管理专家共识（2025版）",
        "source_url": "https://www.guidelines-registry.org/",
        "publish_date": "2025-04-24",
        "version": "2025版",
        "compliance": "CITE",
        "copyright_holder": "共识专家组",
        "redistribution": "可引用，需标注完整出处",
        "peer_reviewed": True,
    },
    {
        "file": "筛查指南2023_全文.txt",
        "publisher": "中国肺癌低剂量CT筛查指南专家组",
        "authority_level": "L2",
        "citation": "中国肺癌低剂量CT筛查指南（2023年版）",
        "source_url": "https://www.ddzxhospital.com/",
        "publish_date": "2023-01-01",
        "version": "2023版",
        "compliance": "CITE",
        "copyright_holder": "指南专家组",
        "redistribution": "可引用，需标注完整出处",
        "peer_reviewed": True,
    },
]


def _manifest_assets(pkg_root: str):
    """★ v2.2：从 `asset_activation_path.ASSET_MANIFEST` 读资产定义。

    与台账**共用同一份清单**（那是本项目完整的资产定义，含全部业务字段）。
    **共享同一个源，asset_id 由构造保证一致。**
    """
    import importlib.util
    here = os.path.dirname(os.path.abspath(__file__))
    spec = importlib.util.spec_from_file_location(
        "_aap_for_manifest", os.path.join(here, "asset_activation_path.py"))
    m = importlib.util.module_from_spec(spec)
    sys.modules["_aap_for_manifest"] = m
    spec.loader.exec_module(m)

    out = []
    for a in m.ASSET_MANIFEST:
        rel = a.get("asset_id_source")
        if not rel:
            continue
        fp = os.path.join(pkg_root, rel)
        if os.path.exists(fp):
            out.append((fp, a))
        else:
            print(f"  [跳过] 未找到 {rel}", file=sys.stderr)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="领域数据资产标识")
    ap.add_argument("--scan", default="/root/onto",
                    help="扫描目录（预设资产所在）")
    # ★ v2.2：从唯一清单派生（与台账同源，ID 必然一致）
    ap.add_argument("--from-manifest", action="store_true",
                    help="从 03_验证与数据/资产清单.json 派生资产")
    _here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument("--pkg-root",
                    default=os.path.dirname(os.path.dirname(_here)),
                    help="提交包根目录")
    ap.add_argument("--out", default="assets.json")
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args()

    reg = AssetRegistry()
    if args.from_manifest:
        for fp, spec in _manifest_assets(args.pkg_root):
            # ★ 把 asset_name 也传进去：否则 register_file 会用磁盘 basename，
            #   与台账的键对不上（曾导致注册表少 1 条）。
            ov = {k: v for k, v in spec.items()
                  if k not in ('asset_id_source', 'role', 'domain',
                               'modality', 'authority_level',
                               'sleeping_form', 'used_in',
                               'activation_status', 'citation',
                               'doi', 'pmcid', 'publisher',
                               'structure_type', 'note',
                               'source_url', 'license_note',
                               'size_note', 'generated_by')}
            reg.register_file(fp, **ov)
        reg.to_json(args.out)
        return 0
    for spec in PRESET_ASSETS:
        path = os.path.join(args.scan, spec["file"])
        if not os.path.exists(path):
            print(f"  [跳过] 未找到 {spec['file']}", file=sys.stderr)
            continue
        overrides = {k: v for k, v in spec.items() if k != "file"}
        reg.register_file(path, **overrides)

    reg.to_json(args.out)

    if args.report:
        print("=" * 72)
        print("  领域数据资产标识 · 注册报告")
        print("=" * 72)
        print(f"  资产总数: {len(reg.assets)}")
        print(f"  输出    : {args.out}")
        print("-" * 72)
        for a in reg.assets.values():
            print(f"\n  【{a.asset_id}】{a.asset_name}")
            print(f"    模态      : {MODALITY.get(a.modality, a.modality)}"
                  f"  ({a.file_format}, {a.size_bytes / 1024:.1f} KB)")
            print(f"    结构      : {a.structure_type}")
            print(f"    来源      : {a.publisher}")
            print(f"    权威等级  : {a.authority_level} — "
                  f"{AUTHORITY_LEVEL.get(a.authority_level, '')}")
            print(f"    时效      : {a.publish_date}  {a.version}"
                  f"  [{FRESHNESS.get(a.freshness, '')}]")
            print(f"    证据等级  : {a.evidence_level} — "
                  f"{EVIDENCE_LEVEL.get(a.evidence_level, '')}")
            if a.strength_distribution:
                dist = "  ".join(f"{k}×{v}"
                                 for k, v in a.strength_distribution.items())
                print(f"    推荐强度  : {dist}")
            print(f"    覆盖条款  : {len(a.clauses)} 条 "
                  f"{','.join(a.clauses[:6])}{'...' if len(a.clauses) > 6 else ''}")
            print(f"    挂载概念  : {len(a.concepts)} 个")
            print(f"    图谱挂载点: {len(a.kg_node_refs)} 个 pno: 节点")
            print(f"    合规      : {a.compliance} — "
                  f"{COMPLIANCE.get(a.compliance, '')}")
            print(f"    含患者数据: {'是' if a.contains_patient_data else '否'}")
            print(f"    处理状态  : {a.status}")
        print("\n" + "=" * 72)

        # 汇总统计
        by_mod = {}
        for a in reg.assets.values():
            by_mod[a.modality] = by_mod.get(a.modality, 0) + 1
        print("\n  按模态分布:", by_mod)
        total_clauses = sorted({c for a in reg.assets.values() for c in a.clauses},
                               key=lambda x: int(re.search(r"\d+", x).group()))
        print(f"  条款总覆盖: {len(total_clauses)} 条 "
              f"{','.join(total_clauses)}")
        all_concepts = {c for a in reg.assets.values() for c in a.concepts}
        print(f"  概念总覆盖: {len(all_concepts)} 个")
    return 0


if __name__ == "__main__":
    sys.exit(main())
