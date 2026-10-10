---
name: lung-nodule-decision
allowed-tools:
  - kg_consult_decision
  - kg_analyze_report_image
  - kg_lookup_concept
  - kg_get_clause
  - kg_find_clauses_by_nodule
  - kg_get_ontology_summary
  - kg_list_clauses
  - knowledge_base_search
description: 肺结节规范处置决策技能。当用户询问肺结节患者「应该如何处理、怎么随访、要不要手术、该不该转诊」等处置决策问题时使用。本技能编排知识图谱多跳推理与指南条文检索，输出带条款级溯源的处置依据链。适用于基层医院、体检中心、社区卫生服务中心的肺结节规范处置场景。
tags:
  - medical
  - lung-nodule
  - clinical-decision
  - knowledge-graph
  - reasoning
---

# 肺结节规范处置决策技能

把「知识图谱多跳推理」与「指南条文检索」编排成一条可溯源的双驱动执行流。

## 分层编排结构

本技能按三层组织，每层职责单一、可独立替换。

| 层 | 名称 | 职责 | 依赖工具 |
|----|------|------|----------|
| L1 | 事实层 | 从自然语言描述抽取结构化患者事实 | kg_consult_decision（内置抽取） |
| L2 | 推理层 | 依据本体定位适用条款、展开处置动作、判定禁忌 | kg_consult_decision |
| L3 | 证据层 | 回检条款原文，补齐条文表述 | knowledge_base_search |

**分层意图**：换行业时只需替换 L2 的本体与 L3 的知识库，L1 的编排骨架不变，实现可复用、可快速部署的 Skill 工作流模板。

## 执行流程

### 第 1 步 抽取患者事实

从用户描述中确认下列信息。**结节直径是硬性必需项**，缺失时必须追问，不可猜测。

| 事实 | 必需 | 说明 |
|------|------|------|
| 结节最大径(mm) | 是 | 缺失则追问，例如「请问结节最大径是多少毫米？」 |
| 密度类型 | 建议 | 实性 / 纯磨玻璃(pGGN) / 混杂性磨玻璃(mGGN) |
| 实性成分(mm) | 建议 | mGGN 的实性成分影响 PET-CT 适用性判定 |
| 年龄、吸烟史 | 建议 | 用于判定是否属肺癌高危人群 |
| 其他危险因素 | 可选 | 职业暴露、慢性肺病、肿瘤史或家族史 |
| 影像特征 | 可选 | 毛刺征、分叶征、胸膜凹陷征、血管集束征、位于上叶 |

术语不确定时先调用 kg_lookup_concept 归一化，例如把「毛玻璃疙瘩」映射为「混杂性磨玻璃结节」。

### 第 2 步 知识图谱推理

调用 **kg_consult_decision**，参数为患者的完整自然语言描述。返回字段：

- conclusion：结论与适用条款
- clause / clause_title / strength：条款编号、标题、推荐强度
- chain：逐跳推理链，每跳标注依据条款
- recommendations：处置动作与检查建议
- follow_up：随访间隔
- contraindications：禁忌与边界提示
- referral：分级诊疗归属
- coverage：COVERED 或 NOT_COVERED
- traceable：是否可溯源

### 第 3 步 条文回检

调用 **knowledge_base_search**，query 用第 2 步得到的 clause_title 或关键特征，取回条款原文表述作为引用依据。

### 第 4 步 组织输出

按下述格式输出，每条建议必须携带条款编号。

## 输出格式

```
一、结节特征归纳
    大小 / 密度类型 / 实性成分 / 危险因素 / 影像特征

二、处置建议
    1. 随访或检查建议 ………………………【推荐意见N】
    2. 进一步评估建议 ………………………【推荐意见N】

三、依据（条款要点）
    【推荐意见N】<条款标题>（<推荐强度>）：<条文要点>

四、边界与提示
    禁忌：<如有，例如 PET-CT 不适用于实性成分≤8mm 的混杂性病灶>【推荐意见N】
    分级诊疗：<基层医院 / 肺结节诊治分中心 / 肺癌防治联盟>
```

## 硬性约束

1. 结节直径缺失时必须追问，禁止用默认值代替。
2. 每条处置建议必须标注【推荐意见N】条款编号。
3. coverage 为 NOT_COVERED 时必须如实回答「指南未覆盖，建议上级医院会诊」，严禁编造条款编号或条文内容。
4. 不给出具体用药名称、剂量与处方。
5. 不给出确定性诊断结论，只提供处置依据与建议。
6. 调用工具时只传工具定义中声明的参数，禁止传递未声明的参数（如 result_key，该参数仅用于 parallel_executor）。
7. 输出结尾须包含：本结果仅供临床参考，不构成诊断结论，不替代医生判断。

## 工具选择规则

| 场景 | 调用 |
|------|------|
| 需要完整处置建议与推理链 | kg_consult_decision |
| 只想知道这类结节对应哪几条条款 | kg_find_clauses_by_nodule |
| 已知条款编号，要展开详情 | kg_get_clause |
| 需要确认术语含义 | kg_lookup_concept |
| 需要说明知识来源与覆盖范围 | kg_get_ontology_summary |
| 用户问「你都能回答什么」 | kg_list_clauses |
| 需要条款原文表述 | knowledge_base_search |
| **用户提供报告图片**（而非文字描述） | **kg_analyze_report_image** |

## 使用方式

<code>
result = kg_consult_decision(description="55岁男性，8mm混合磨玻璃结节，实性成分2mm，吸烟30年")
print(result["conclusion"])
print(result["clause"], result["follow_up"])
for step in result["chain"]:
    print(step["hop"], step["rule"], step.get("clause", ""))
</code>

## 示例

输入：
> 一位 55 岁男性，8mm 混合磨玻璃结节，实性成分 2mm，吸烟 30 年，该怎么随访？

执行：
1. kg_consult_decision(description="55岁男性，8mm混合磨玻璃结节，实性成分2mm，吸烟30年")
2. knowledge_base_search(query="mGGN ≤8mm 随访")

输出要点：

```
一、结节特征归纳
    直径 8mm；混杂性磨玻璃结节(mGGN)；实性成分 2mm；55岁，吸烟30年（符合高危人群）

二、处置建议
    1. 在 3、6、12 和 24 个月进行胸部 CT 随访 ……………【推荐意见14】
    2. 建议应用 AI 和人机 MDT 评估 ………………………【推荐意见14】
    3. 无变化者随后转为常规年度随访 ………………………【推荐意见14】

三、依据（条款要点）
    【推荐意见14】（Ⅲ类推荐）：孤立性mGGN直径≤8mm者，建议在3、6、12和24个月
    进行CT随访，建议应用AI和人机MDT评估，无变化者随后转为常规年度随访。

四、边界与提示
    禁忌：PET-CT 不推荐用于判断实性成分≤8mm 的混杂性病灶 ……【推荐意见15】①
    分级诊疗：建议转肺结节诊治分中心管理 ………………………【推荐意见18】②
    提示：若随访中出现结节增大或实性成分增多，需考虑切除而非非手术活检。

本结果仅供临床参考，不构成诊断结论，不替代医生判断。
```

## 拒答示例

输入：
> 我有肺结节，该怎么办？

正确行为：追问缺失的必需信息，不直接给建议。

> 为了给出规范建议，我需要确认几个信息：请问结节的最大径是多少毫米？是实性、纯磨玻璃，还是混杂性磨玻璃结节？

## 错误处理

| 错误 | 原因 | 解决方案 |
|------|------|----------|
| coverage=NOT_COVERED 且 missing_fields 含 diameter_mm | 描述缺少结节直径 | 向用户追问最大径 |
| kg_lookup_concept 返回 matched=false | 术语不在本体中 | 使用返回的 available_concepts 中的规范术语重试 |
| kg_get_clause 返回 found=false | 条款编号不存在 | 使用返回的 available_clauses 中的编号 |
