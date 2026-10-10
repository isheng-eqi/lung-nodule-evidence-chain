#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从共识条款生成结构化表格数据资产（表格模态）
================================================================

对应赛题"表格"多模态要求。

把《肺结节诊治中国专家共识（2024年版）》的 18 条推荐意见，
从散文条款转化为**结构化表格**，用于：
  1. 作为知识库的表格类数据资产（演示"表格"模态）
  2. 作为推理引擎的规则校验基准
  3. 作为评测集的可读金标准

输出：
  clauses_table.csv     —— CSV 表格（结构化数据资产）
  clauses_table.md      —— Markdown 表格（可读版本）

用法：
    python3 build_clause_table.py --out-dir .
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys


# ============================================================================
# 条款结构化数据（来源：共识 18 条推荐意见，逐条人工结构化）
# 字段设计对应本体的对象属性与数据属性，便于图谱回填校验
# ============================================================================

CLAUSES = [
    {
        "clause": "推荐意见1", "title": "难定性肺结节",
        "strength": "Ⅲ类推荐",
        "applicable_nodule": "难定性肺结节",
        "density_type": "不限", "size_min_mm": "", "size_max_mm": "",
        "risk_factor_condition": "不限",
        "recommended_action": "MDT工作模式和医患共同决策",
        "examination": "", "follow_up_interval": "",
        "next_step": "", "contraindication": "",
        "key_point": "无法通过非手术活检明确诊断且高度怀疑早期肺癌者，采用MDT与医患共同决策",
    },
    {
        "clause": "推荐意见2", "title": "肺癌高危人群定义与筛查",
        "strength": "Ⅱ类推荐",
        "applicable_nodule": "肺癌高危人群",
        "density_type": "不限", "size_min_mm": "", "size_max_mm": "",
        "risk_factor_condition": "年龄≥40岁 且 具有任一危险因素",
        "recommended_action": "每年LDCT筛查",
        "examination": "低剂量CT（LDCT）", "follow_up_interval": "每年一次",
        "next_step": "", "contraindication": "",
        "key_point": "危险因素：①吸烟指数≥400年支或20包年；②环境或高危职业暴露史；③合并慢阻肺、弥漫性肺纤维化或曾患肺结核；④曾患恶性肿瘤或肺癌家族史",
    },
    {
        "clause": "推荐意见3", "title": "薄层CT与历史影像对比",
        "strength": "ⅠB类推荐",
        "applicable_nodule": "筛查或机会发现的肺结节",
        "density_type": "不限", "size_min_mm": "", "size_max_mm": "",
        "risk_factor_condition": "不限",
        "recommended_action": "对病灶处行薄层CT或薄层高分辨CT，并与既往历史影像学资料对比",
        "examination": "薄层CT / 薄层高分辨CT", "follow_up_interval": "",
        "next_step": "", "contraindication": "",
        "key_point": "薄层扫描以更好显示结节特征；必须与既往影像对比",
    },
    {
        "clause": "推荐意见4", "title": "AI辅助诊断与肿瘤标志物",
        "strength": "Ⅱ类推荐",
        "applicable_nodule": "肺结节",
        "density_type": "不限", "size_min_mm": "", "size_max_mm": "",
        "risk_factor_condition": "不限",
        "recommended_action": "AI辅助影像诊断；采用LCBP模型评估恶性风险",
        "examination": "肿瘤标志物组合（ProGRP/SCC/CEA/Cyfra21-1）",
        "follow_up_interval": "",
        "next_step": "", "contraindication": "不推荐单一肿瘤标志物作为亚厘米小结节和微小结节的筛查评估指标",
        "key_point": "LCBP模型预测恶性风险优于ACCP模型",
    },
    {
        "clause": "推荐意见5", "title": ">8mm结节恶性概率评估",
        "strength": "Ⅱ类推荐",
        "applicable_nodule": "孤立性不明原因结节",
        "density_type": "实性肺结节", "size_min_mm": 8, "size_max_mm": 30,
        "risk_factor_condition": "不限",
        "recommended_action": "定性使用临床判断和（或）定量使用验证模型评估恶性概率",
        "examination": "PET-CT / CAC检测", "follow_up_interval": "",
        "next_step": "低中度概率(5%~65%)可考虑PET-CT；高度(>65%)可直接PET-CT",
        "contraindication": "",
        "key_point": "要求个体化诊疗者可推荐CAC辅助评估",
    },
    {
        "clause": "推荐意见6", "title": "风险获益沟通与患者意愿",
        "strength": "Ⅱ类推荐",
        "applicable_nodule": "孤立性不明原因结节",
        "density_type": "实性肺结节", "size_min_mm": 8, "size_max_mm": 30,
        "risk_factor_condition": "不限",
        "recommended_action": "提出管理策略的风险和益处，并考虑患者意愿而决定",
        "examination": "", "follow_up_interval": "",
        "next_step": "", "contraindication": "",
        "key_point": "管理策略包括影像学随访、非手术活检或手术",
    },
    {
        "clause": "推荐意见7", "title": ">8mm结节随访间隔",
        "strength": "Ⅱ类推荐",
        "applicable_nodule": "孤立性不明原因结节",
        "density_type": "实性肺结节", "size_min_mm": 8, "size_max_mm": 30,
        "risk_factor_condition": "临床恶性概率很低(<5%)等4种情形",
        "recommended_action": "薄层CT扫描随访",
        "examination": "薄层CT", "follow_up_interval": "3~6个月、9~12个月、18~24个月",
        "next_step": "", "contraindication": "",
        "key_point": "适用情形：①临床恶性概率<5%；②概率低且功能成像阴性；③穿刺活检未确诊；④患者倾向非侵入性管理",
    },
    {
        "clause": "推荐意见8", "title": "非手术活检指征",
        "strength": "Ⅱ类推荐",
        "applicable_nodule": "孤立性不明原因结节",
        "density_type": "实性肺结节", "size_min_mm": 8, "size_max_mm": 30,
        "risk_factor_condition": "不限",
        "recommended_action": "非手术活检",
        "examination": "非手术活检", "follow_up_interval": "",
        "next_step": "手段选择基于结节大小位置、并发症风险、技术可行性与术者熟练程度",
        "contraindication": "",
        "key_point": "适用情形：临床预测与影像不一致；恶性概率低中度(10%~60%)；疑诊需特定治疗的良性疾病；患者希望术前证实",
    },
    {
        "clause": "推荐意见9", "title": "手术活检指征",
        "strength": "Ⅱ类推荐",
        "applicable_nodule": "孤立性不明原因结节",
        "density_type": "实性肺结节", "size_min_mm": 8, "size_max_mm": 30,
        "risk_factor_condition": "不限",
        "recommended_action": "手术活检诊断",
        "examination": "手术活检", "follow_up_interval": "",
        "next_step": "胸腔镜检查",
        "contraindication": "不推荐单纯为诊断目的而对单个肺结节进行手术活检",
        "key_point": "适用：临床恶性概率高(>65%)；PET-CT高代谢；非手术活检可疑恶性；患者愿意接受手术",
    },
    {
        "clause": "推荐意见10", "title": "≤8mm实性结节（无危险因素）随访",
        "strength": "Ⅱ类推荐",
        "applicable_nodule": "孤立性实性结节",
        "density_type": "实性肺结节", "size_min_mm": 0, "size_max_mm": 8,
        "risk_factor_condition": "无肺癌危险因素",
        "recommended_action": "根据结节大小选择CT随访频率与持续时间",
        "examination": "CT", "follow_up_interval": "≤4mm:遵医嘱或不随访；4~6mm:常规年度；6~8mm:2年内6~12个月，未变化转常规年度",
        "next_step": "", "contraindication": "",
        "key_point": "≤4mm若不随访应告知患者潜在危害",
    },
    {
        "clause": "推荐意见11", "title": "≤8mm实性结节（有危险因素）随访",
        "strength": "Ⅱ类推荐",
        "applicable_nodule": "孤立性实性结节",
        "density_type": "实性肺结节", "size_min_mm": 0, "size_max_mm": 8,
        "risk_factor_condition": "存在一项或更多肺癌危险因素",
        "recommended_action": "根据结节大小选择CT随访频率与持续时间",
        "examination": "CT", "follow_up_interval": "≤4mm:常规年度；4~6mm:6~12个月，未变化则18~24个月，其后转常规年度；6~8mm:3~6个月、9~12个月，其后每6个月，2年无变化转常规年度",
        "next_step": "", "contraindication": "",
        "key_point": "有危险因素者的随访频率明显高于无危险因素者",
    },
    {
        "clause": "推荐意见12", "title": "pGGN≤5mm随访",
        "strength": "Ⅱ类推荐",
        "applicable_nodule": "纯磨玻璃结节（pGGN）",
        "density_type": "纯磨玻璃结节", "size_min_mm": 0, "size_max_mm": 5,
        "risk_factor_condition": "不限",
        "recommended_action": "CT随访",
        "examination": "胸部CT", "follow_up_interval": "首次6个月，随后年度",
        "next_step": "", "contraindication": "",
        "key_point": "pGGN以5mm大小为界进行分类管理",
    },
    {
        "clause": "推荐意见13", "title": "pGGN 5~10mm随访",
        "strength": "Ⅲ类推荐",
        "applicable_nodule": "纯磨玻璃结节（pGGN）",
        "density_type": "纯磨玻璃结节", "size_min_mm": 5, "size_max_mm": 10,
        "risk_factor_condition": "不限",
        "recommended_action": "CT随访，建议应用AI和人机MDT评估，可辅以CAC评估，据结果推荐非手术活检和（或）手术切除",
        "examination": "胸部CT / CAC检测 / 薄层平扫",
        "follow_up_interval": "首次3个月，随后6个月",
        "next_step": "非手术活检和（或）手术切除",
        "contraindication": "",
        "key_point": "若结节增大（尤>10mm）或实性成分增加，通常预示恶性转化；若合并危及生命疾病可限定随访时间或减少频率",
    },
    {
        "clause": "推荐意见14", "title": "mGGN≤8mm随访",
        "strength": "Ⅲ类推荐",
        "applicable_nodule": "混杂性磨玻璃结节（mGGN）",
        "density_type": "混杂性磨玻璃结节", "size_min_mm": 0, "size_max_mm": 8,
        "risk_factor_condition": "不限",
        "recommended_action": "CT随访，建议应用AI和人机MDT评估，可辅以CAC评估，无变化者随后转为常规年度随访",
        "examination": "胸部CT / 薄层平扫 / CAC检测",
        "follow_up_interval": "3、6、12和24个月",
        "next_step": "若增大或实性成分增多需考虑切除（而非非手术活检）；有症状或细菌感染征象可考虑经验性抗菌治疗",
        "contraindication": "",
        "key_point": "内部实性成分比例对侵袭性判断比大小更重要",
    },
    {
        "clause": "推荐意见15", "title": "mGGN>8mm处置",
        "strength": "Ⅲ类推荐",
        "applicable_nodule": "混杂性磨玻璃结节（mGGN）",
        "density_type": "混杂性磨玻璃结节", "size_min_mm": 8, "size_max_mm": 30,
        "risk_factor_condition": "不限",
        "recommended_action": "3个月重复胸部CT，适当考虑经验性抗生素治疗；持续存在者应用AI和人机MDT评估，可辅以CAC或PET-CT，必要者非手术活检和（或）手术切除",
        "examination": "胸部CT / CAC检测 / PET-CT / 非手术活检",
        "follow_up_interval": "3个月",
        "next_step": "非手术活检和（或）手术切除；直径>15mm者可直接考虑PET-CT、非手术活检和（或）手术切除",
        "contraindication": "PET-CT不推荐用于判断实性成分≤8mm的混杂性病灶",
        "key_point": "PET-CT对pGGN及实性成分≤8mm肺结节鉴别诊断无明显优势",
    },
    {
        "clause": "推荐意见16", "title": "多发性肺结节评估",
        "strength": "Ⅲ类推荐",
        "applicable_nodule": "多发性肺结节",
        "density_type": "不限", "size_min_mm": "", "size_max_mm": "",
        "risk_factor_condition": "不限",
        "recommended_action": "单独评估每个结节，建议应用AI和人机MDT评估，可辅以CAC或PET-CT评估",
        "examination": "CAC检测 / PET-CT", "follow_up_interval": "",
        "next_step": "", "contraindication": "除非有组织病理学证实转移，否则不可否定根治性治疗",
        "key_point": "对于多发性pGGN，至少1个病变直径>5mm需重点关注",
    },
    {
        "clause": "推荐意见17", "title": "肺癌局部治疗",
        "strength": "ⅠA类推荐",
        "applicable_nodule": "肺癌",
        "density_type": "不限", "size_min_mm": "", "size_max_mm": "",
        "risk_factor_condition": "不限",
        "recommended_action": "外科手术根治性切除",
        "examination": "", "follow_up_interval": "",
        "next_step": "心肺功能不能耐受者，经MDT评估和医患共同决策可考虑SBRT或消融治疗",
        "contraindication": "",
        "key_point": "肺癌的优选局部治疗方式为外科手术根治性切除（ⅠA类推荐）",
    },
    {
        "clause": "推荐意见18", "title": "分级诊疗管理",
        "strength": "Ⅲ类推荐",
        "applicable_nodule": "肺结节",
        "density_type": "不限", "size_min_mm": 0, "size_max_mm": 30,
        "risk_factor_condition": "不限",
        "recommended_action": "按分级诊疗原则管理：≤5mm在基层医院管理；5~10mm且未明确诊断者转分中心；>10mm且分中心未明确诊断者由联盟协助指导",
        "examination": "", "follow_up_interval": "",
        "next_step": "转诊", "contraindication": "",
        "key_point": "基于物联网医学平台，端口开放质控",
    },
]

FIELDNAMES = [
    "clause", "title", "strength", "applicable_nodule", "density_type",
    "size_min_mm", "size_max_mm", "risk_factor_condition",
    "recommended_action", "examination", "follow_up_interval",
    "next_step", "contraindication", "key_point",
]

HEADER_ZH = {
    "clause": "条款编号", "title": "条款标题", "strength": "推荐强度",
    "applicable_nodule": "适用结节类型", "density_type": "密度类型",
    "size_min_mm": "直径下限(mm)", "size_max_mm": "直径上限(mm)",
    "risk_factor_condition": "危险因素条件",
    "recommended_action": "推荐处置", "examination": "检查手段",
    "follow_up_interval": "随访间隔", "next_step": "后续步骤",
    "contraindication": "禁忌与不推荐", "key_point": "要点",
}


def main() -> int:
    ap = argparse.ArgumentParser(description="生成条款结构化表格资产")
    ap.add_argument("--out-dir", default=".")
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)

    # ---- CSV ----
    csv_path = os.path.join(args.out_dir, "clauses_table.csv")
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES)
        w.writerow({k: HEADER_ZH[k] for k in FIELDNAMES})
        for c in CLAUSES:
            w.writerow({k: c.get(k, "") for k in FIELDNAMES})

    # ---- Markdown ----
    md_path = os.path.join(args.out_dir, "clauses_table.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# 肺结节诊治中国专家共识（2024年版）推荐意见结构化表\n\n")
        f.write("> 数据来源：中华医学会呼吸病学分会、中国肺癌防治联盟专家组，"
                "中华结核和呼吸杂志, 2024, 47(8): 716-729。\n")
        f.write("> 本表将 18 条推荐意见由条款文本转为结构化数据，"
                "供知识图谱回填校验与评测使用。\n\n")
        f.write("| " + " | ".join(HEADER_ZH[k] for k in FIELDNAMES) + " |\n")
        f.write("|" + "---|" * len(FIELDNAMES) + "\n")
        for c in CLAUSES:
            row = []
            for k in FIELDNAMES:
                v = str(c.get(k, "")).replace("|", "\\|").replace("\n", " ")
                row.append(v)
            f.write("| " + " | ".join(row) + " |\n")

    # ---- 统计 ----
    strength_dist: dict[str, int] = {}
    for c in CLAUSES:
        strength_dist[c["strength"]] = strength_dist.get(c["strength"], 0) + 1
    density_dist: dict[str, int] = {}
    for c in CLAUSES:
        d = c["density_type"] or "不限"
        density_dist[d] = density_dist.get(d, 0) + 1
    with_followup = sum(1 for c in CLAUSES if c["follow_up_interval"])
    with_contra = sum(1 for c in CLAUSES if c["contraindication"])

    print("=" * 66)
    print("  条款结构化表格资产 · 生成报告")
    print("=" * 66)
    print(f"  条款数        : {len(CLAUSES)}")
    print(f"  字段数        : {len(FIELDNAMES)}")
    print(f"  含随访间隔条款 : {with_followup}")
    print(f"  含禁忌条款    : {with_contra}")
    print(f"  推荐强度分布  : {strength_dist}")
    print(f"  密度类型分布  : {density_dist}")
    print("-" * 66)
    print(f"  CSV  : {csv_path}  ({os.path.getsize(csv_path)} 字节)")
    print(f"  MD   : {md_path}  ({os.path.getsize(md_path)} 字节)")
    print("=" * 66)
    return 0


if __name__ == "__main__":
    sys.exit(main())
