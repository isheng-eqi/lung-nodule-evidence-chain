#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
国赛答辩 PPT 生成器
================================================================

把《国赛答辩框架》转为可编辑的 .pptx 文件。

设计要点：
  · 16:9 版式（1920×1080 对应 13.333×7.5 英寸）
  · 中文优先字体（思源黑体 / 微软雅黑 / 苹方 回退链）
  · 深色标题 + 浅色正文，保证投影可读性
  · 关键数字用强调色标出
  · 每页标注对应的**评分项**（便于答辩时控场）
  · 备注栏写入**讲解要点**（演讲者视图可见）

用法：
    python3 build_defense_ppt.py --out 答辩PPT.pptx
"""

from __future__ import annotations

import argparse
import os
import sys

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR

# ============================================================================
# 视觉规范
# ============================================================================

C_PRIMARY = RGBColor(0x1A, 0x36, 0x5D)     # 深蓝（标题）
C_ACCENT = RGBColor(0xC0, 0x39, 0x2B)      # 强调红（关键数字）
C_ACCENT2 = RGBColor(0x1F, 0x7A, 0x4D)     # 强调绿（正向指标）
C_TEXT = RGBColor(0x2B, 0x2B, 0x2B)        # 正文
C_MUTED = RGBColor(0x6B, 0x6B, 0x6B)       # 次要文字
C_LIGHT = RGBColor(0xF2, 0xF5, 0xF9)       # 浅底
C_WHITE = RGBColor(0xFF, 0xFF, 0xFF)
C_BORDER = RGBColor(0xD5, 0xDD, 0xE5)

FONT = "Microsoft YaHei"        # 微软雅黑（Windows 通用）
FONT_FALLBACK = "SimHei"

SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)


# ============================================================================
# 基础工具
# ============================================================================

class Deck:
    def __init__(self) -> None:
        self.prs = Presentation()
        self.prs.slide_width = SLIDE_W
        self.prs.slide_height = SLIDE_H
        self.blank = self.prs.slide_layouts[6]   # 空白版式
        self.page_no = 0

    # ---------- 页面骨架 ----------
    def slide(self, title: str = "", rubric: str = "", notes: str = ""):
        """新建一页。rubric = 对应评分项；notes = 演讲者备注。"""
        s = self.prs.slides.add_slide(self.blank)
        self.page_no += 1

        # 顶部标题条
        if title:
            bar = s.shapes.add_shape(1, Inches(0), Inches(0),
                                     SLIDE_W, Inches(1.0))
            bar.fill.solid(); bar.fill.fore_color.rgb = C_PRIMARY
            bar.line.fill.background()
            tf = bar.text_frame
            tf.margin_left = Inches(0.55); tf.margin_top = Inches(0.16)
            tf.vertical_anchor = MSO_ANCHOR.MIDDLE
            p = tf.paragraphs[0]
            p.text = title
            p.font.size = Pt(28); p.font.bold = True
            p.font.color.rgb = C_WHITE; p.font.name = FONT

        # 右上角评分项标签
        if rubric:
            tag = s.shapes.add_textbox(SLIDE_W - Inches(4.2), Inches(1.08),
                                       Inches(3.9), Inches(0.34))
            tp = tag.text_frame.paragraphs[0]
            tp.text = f"▸ {rubric}"
            tp.alignment = PP_ALIGN.RIGHT
            tp.font.size = Pt(11); tp.font.color.rgb = C_MUTED
            tp.font.name = FONT

        # 页码
        pn = s.shapes.add_textbox(SLIDE_W - Inches(1.2), SLIDE_H - Inches(0.45),
                                  Inches(1.0), Inches(0.3))
        pp = pn.text_frame.paragraphs[0]
        pp.text = f"{self.page_no}"
        pp.alignment = PP_ALIGN.RIGHT
        pp.font.size = Pt(11); pp.font.color.rgb = C_MUTED

        # 演讲者备注
        if notes:
            s.notes_slide.notes_text_frame.text = notes
        return s

    # ---------- 文本块 ----------
    def text(self, s, x, y, w, h, lines, size=16, color=C_TEXT,
             bold=False, align=PP_ALIGN.LEFT, spacing=6.0, line_spacing=1.15):
        """lines: str 或 [(文本, {覆盖属性}), ...]"""
        box = s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
        tf = box.text_frame
        tf.word_wrap = True
        if isinstance(lines, str):
            lines = [lines]
        for i, item in enumerate(lines):
            ov = {}
            if isinstance(item, tuple):
                item, ov = item
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.text = str(item)
            p.alignment = ov.get("align", align)
            p.space_after = Pt(ov.get("spacing", spacing))
            p.line_spacing = ov.get("line_spacing", line_spacing)
            for r in p.runs:
                r.font.size = Pt(ov.get("size", size))
                r.font.bold = ov.get("bold", bold)
                r.font.color.rgb = ov.get("color", color)
                r.font.name = FONT
        return box

    # ---------- 表格 ----------
    def table(self, s, x, y, w, h, data, col_w=None,
              head_size=13, body_size=12, first_col_bold=False):
        rows, cols = len(data), len(data[0])
        shp = s.shapes.add_table(rows, cols, Inches(x), Inches(y),
                                 Inches(w), Inches(h))
        tbl = shp.table
        if col_w:
            total = sum(col_w)
            for i, cw in enumerate(col_w):
                tbl.columns[i].width = Emu(int(Inches(w) * cw / total))
        for r in range(rows):
            for c in range(cols):
                cell = tbl.cell(r, c)
                cell.text = str(data[r][c])
                cell.margin_left = Inches(0.07); cell.margin_right = Inches(0.07)
                cell.margin_top = Inches(0.03); cell.margin_bottom = Inches(0.03)
                cell.vertical_anchor = MSO_ANCHOR.MIDDLE
                cell.fill.solid()
                cell.fill.fore_color.rgb = C_PRIMARY if r == 0 else (
                    C_LIGHT if r % 2 == 0 else C_WHITE)
                for p in cell.text_frame.paragraphs:
                    for run in p.runs:
                        run.font.name = FONT
                        run.font.size = Pt(head_size if r == 0 else body_size)
                        run.font.bold = (r == 0) or (first_col_bold and c == 0)
                        run.font.color.rgb = C_WHITE if r == 0 else C_TEXT
        return tbl

    # ---------- 强调数字卡 ----------
    def stat_cards(self, s, y, items, x0=0.7, gap=0.3, total_w=12.0):
        """items: [(大数字, 说明)]，横向排布"""
        n = len(items)
        cw = (total_w - gap * (n - 1)) / n
        for i, (big, label) in enumerate(items):
            x = x0 + i * (cw + gap)
            card = s.shapes.add_shape(1, Inches(x), Inches(y),
                                      Inches(cw), Inches(1.5))
            card.fill.solid(); card.fill.fore_color.rgb = C_LIGHT
            card.line.color.rgb = C_BORDER; card.line.width = Pt(0.75)
            tf = card.text_frame
            tf.margin_top = Inches(0.12); tf.margin_bottom = Inches(0.08)
            tf.vertical_anchor = MSO_ANCHOR.MIDDLE
            p1 = tf.paragraphs[0]
            p1.text = str(big); p1.alignment = PP_ALIGN.CENTER
            p1.font.size = Pt(26); p1.font.bold = True
            p1.font.color.rgb = C_ACCENT; p1.font.name = FONT
            p2 = tf.add_paragraph()
            p2.text = label; p2.alignment = PP_ALIGN.CENTER
            p2.font.size = Pt(11); p2.font.color.rgb = C_MUTED
            p2.font.name = FONT

    # ---------- 代码框 ----------
    def code(self, s, x, y, w, h, code_text, size=11):
        box = s.shapes.add_shape(1, Inches(x), Inches(y), Inches(w), Inches(h))
        box.fill.solid(); box.fill.fore_color.rgb = RGBColor(0xF7, 0xF7, 0xF4)
        box.line.color.rgb = C_BORDER; box.line.width = Pt(0.75)
        tf = box.text_frame
        tf.word_wrap = True
        tf.margin_left = Inches(0.14); tf.margin_top = Inches(0.1)
        tf.margin_right = Inches(0.1); tf.margin_bottom = Inches(0.1)
        for i, line in enumerate(code_text.split("\n")):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.text = line
            p.space_after = Pt(1); p.line_spacing = 1.0
            for r in p.runs:
                r.font.size = Pt(size)
                r.font.name = "Consolas"
                r.font.color.rgb = (C_ACCENT2 if line.strip().startswith("#")
                                    else C_TEXT)
        return box

    # ---------- 流程箭头图 ----------
    def flow(self, s, y, steps, x0=0.7, total_w=12.0, h=0.85, size=13):
        n = len(steps)
        gap = 0.22
        cw = (total_w - gap * (n - 1)) / n
        for i, txt in enumerate(steps):
            x = x0 + i * (cw + gap)
            sh = s.shapes.add_shape(1, Inches(x), Inches(y), Inches(cw), Inches(h))
            sh.fill.solid()
            sh.fill.fore_color.rgb = C_PRIMARY if i % 2 == 0 else RGBColor(0x2E, 0x5C, 0x8A)
            sh.line.fill.background()
            tf = sh.text_frame; tf.word_wrap = True
            tf.vertical_anchor = MSO_ANCHOR.MIDDLE
            p = tf.paragraphs[0]; p.text = txt
            p.alignment = PP_ALIGN.CENTER
            p.font.size = Pt(size); p.font.color.rgb = C_WHITE; p.font.name = FONT
            if i < n - 1:
                ar = s.shapes.add_textbox(Inches(x + cw), Inches(y + 0.12),
                                          Inches(gap), Inches(h))
                ap = ar.text_frame.paragraphs[0]
                ap.text = "▶"; ap.alignment = PP_ALIGN.CENTER
                ap.font.size = Pt(14); ap.font.color.rgb = C_MUTED

    def save(self, path: str) -> str:
        self.prs.save(path)
        return path


# ============================================================================
# 逐页构建
# ============================================================================

def build(out: str) -> str:
    d = Deck()

    # ---------------- P1 封面 ----------------
    s = d.slide()
    bg = s.shapes.add_shape(1, Inches(0), Inches(0), SLIDE_W, SLIDE_H)
    bg.fill.solid(); bg.fill.fore_color.rgb = C_PRIMARY; bg.line.fill.background()

    d.text(s, 1.0, 1.9, 11.3, 1.6, "基层肺结节处置依据链",
           size=44, color=C_WHITE, bold=True, align=PP_ALIGN.CENTER)
    d.text(s, 1.0, 3.35, 11.3, 0.9, "—— 让指南在诊室里可执行、可追溯",
           size=22, color=RGBColor(0xBF, 0xD4, 0xEA), align=PP_ALIGN.CENTER)
    ln = s.shapes.add_shape(1, Inches(5.4), Inches(4.35), Inches(2.5), Pt(2))
    ln.fill.solid(); ln.fill.fore_color.rgb = RGBColor(0x7F, 0xA6, 0xCC)
    ln.line.fill.background()
    d.text(s, 1.0, 4.6, 11.3, 1.4, [
        "赛题3：基于华为 ModelEngine Nexent 打造可进化决策智能体",
        "第十一届华为ICT大赛 · 中国总决赛答辩",
        "〔学校名称〕 · 〔队伍名称〕",
    ], size=15, color=RGBColor(0xD6, 0xE3, 0xF0), align=PP_ALIGN.CENTER, spacing=8)
    s.notes_slide.notes_text_frame.text = (
        "开场 1.5 分钟。先讲问题，不讲技术。\n"
        "一句话主张：基层医生不缺指南，缺的是一条能照着做、"
        "也能证明自己没做错的依据链。")

    # ---------------- P2 问题：三段事实 ----------------
    s = d.slide("一、问题：从“发现结节”到“给出处置”之间的空白带",
                "业务价值（15%）",
                "讲三段事实时不要展开技术，让评委先建立问题认知。约 1 分钟。")
    d.table(s, 0.7, 1.75, 11.9, 2.3, [
        ["#", "事实", "后果"],
        ["1", "影像 AI 能发现结节，但输出止于筛查报告", "不回答“该怎么办”"],
        ["2", "指南写清了该怎么办，但它是给人读的散文", "无法映射到每一份具体报告"],
        ["3", "大模型答得够准，但答案不可审计", "医生无法拿没有出处的建议为自己负责"],
    ], col_w=[0.5, 6.0, 5.4], head_size=14, body_size=13)

    bx = s.shapes.add_shape(1, Inches(0.7), Inches(4.35), Inches(11.9), Inches(1.15))
    bx.fill.solid(); bx.fill.fore_color.rgb = C_LIGHT
    bx.line.color.rgb = C_ACCENT; bx.line.width = Pt(1.25)
    tf = bx.text_frame; tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.text = "三者叠加，形成了“检测之后、决策之前”的空白带"
    p.alignment = PP_ALIGN.CENTER
    p.font.size = Pt(20); p.font.bold = True
    p.font.color.rgb = C_PRIMARY; p.font.name = FONT

    d.text(s, 0.7, 5.75, 11.9, 0.8,
           [("一句话主张：基层医生不缺指南，缺的是一条能照着做、"
             "也能证明自己没做错的依据链", {"size": 17, "bold": True, "color": C_ACCENT})])

    # ---------------- P3 事实佐证 ----------------
    s = d.slide("二、这不是小众问题 —— 共性断层", "业务价值（15%）",
                "用一个类比把问题从医疗推广到其他行业，为最后的“通用推广价值”铺垫。")
    d.text(s, 0.7, 1.7, 11.9, 0.5,
           "四个行业的文档形态高度相似：都是「条款化规范 + 阈值条件 + 处置动作」",
           size=15, color=C_MUTED)
    d.table(s, 0.7, 2.35, 11.9, 2.6, [
        ["行业", "同样的断层"],
        ["医疗", "指南写清了怎么办，但诊室里只有 3 分钟，指南是 14 页散文"],
        ["金融", "信贷政策写得清楚，但客户经理无法为每笔业务逐条比对政策"],
        ["制造", "设备手册有处置流程，但一线工人不会在故障时翻手册"],
        ["政务", "办事指南公布在网上，但窗口人员仍靠经验判断材料是否齐全"],
    ], col_w=[1.6, 10.3], head_size=14, body_size=13, first_col_bold=True)
    d.text(s, 0.7, 5.25, 11.9, 0.9,
           [("本项目的贡献不是“做了一个肺结节智能体”，"
             "而是把“从行业文档到可执行知识”做成了一条可复制的流水线。",
             {"size": 17, "bold": True, "color": C_PRIMARY})])

    # ---------------- P4 系统架构 ----------------
    s = d.slide("三、整体方案：四层架构 + 检索-推理双驱动", "编排与 MCP/Skill 集成（15%）",
                "重点讲“为什么不重复造检索”。约 1 分钟。")
    d.table(s, 0.7, 1.7, 11.9, 3.2, [
        ["层", "组成", "提供方"],
        ["应用层", "肺结节规范处置智能体（面向县级医院与社区医生）", "本项目"],
        ["平台层", "Agent 运行时 · 知识库检索 · MCP 生态 · 分层记忆", "Nexent"],
        ["平台层", "领域本体 · 知识图谱 · 多跳推理 · 条款溯源 · 6 个 MCP 工具 · Skill 编排", "本项目自研"],
        ["数据层", "3 份公开指南 + 1 份结构化表格 + 1 份影像报告样例", "公开资料"],
    ], col_w=[1.5, 8.2, 2.2], head_size=14, body_size=12.5)

    bx = s.shapes.add_shape(1, Inches(0.7), Inches(5.15), Inches(11.9), Inches(1.15))
    bx.fill.solid(); bx.fill.fore_color.rgb = C_LIGHT
    bx.line.color.rgb = C_BORDER
    tf = bx.text_frame; tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.text = ("平台提供了检索能力，但没有结构化的领域推理能力。\n"
              "我们没有重复造检索，而是在平台的空白处补上图谱推理与条款级溯源。")
    p.alignment = PP_ALIGN.CENTER
    p.font.size = Pt(15); p.font.color.rgb = C_TEXT; p.font.name = FONT

    # ---------------- P5 能力归属 ----------------
    s = d.slide("四、能力归属：主动划清边界", "编排与 MCP/Skill 集成（15%）",
                "这一页很重要 —— 主动说明哪些是平台的、哪些是我们做的，比让评委追问更显专业。")
    d.table(s, 0.7, 1.75, 5.7, 3.9, [
        ["Nexent 平台提供"],
        ["Agent 运行时与编排"],
        ["知识库检索（三模式 + rerank）"],
        ["引用溯源（知识级）"],
        ["MCP 工具生态与管理"],
        ["分层记忆"],
        ["Elasticsearch 向量检索"],
        ["多模态模型接入"],
    ], col_w=[1], head_size=14, body_size=13)
    d.table(s, 6.9, 1.75, 5.7, 3.9, [
        ["本项目自研"],
        ["领域本体（OWL，57 类）"],
        ["知识图谱（三元组 + 多跳推理）"],
        ["条款级溯源与拒答兜底"],
        ["6 个 MCP 工具"],
        ["Skill 三层编排"],
        ["本体半自动化构建算法"],
        ["语料清洗与数据治理"],
    ], col_w=[1], head_size=14, body_size=13)
    d.text(s, 0.7, 5.85, 11.9, 0.6,
           [("平台能力 + 自研增量 = 检索-推理双驱动",
             {"size": 16, "bold": True, "color": C_ACCENT2, "align": PP_ALIGN.CENTER})])

    # ---------------- P6 知识图谱构建挑战 ----------------
    s = d.slide("五、知识图谱构建：低资源场景的挑战", "算法创新性（15%）",
                "先讲挑战，再讲方案。约 40 秒。")
    d.text(s, 0.7, 1.8, 11.9, 3.6, [
        ("① 临床领域没有公开的标准本体", {"size": 19, "bold": True, "color": C_PRIMARY, "spacing": 4}),
        ("    通用本体（如 SNOMED）覆盖广但不含“指南条款”这一层结构", {"size": 13, "color": C_MUTED, "spacing": 18}),
        ("② 人工构建本体成本极高", {"size": 19, "bold": True, "color": C_PRIMARY, "spacing": 4}),
        ("    需要临床专家逐条梳理，按 90 秒/三元组估算，单份共识需 3 小时以上", {"size": 13, "color": C_MUTED, "spacing": 18}),
        ("③ 指南更新快，本体需要持续演进", {"size": 19, "bold": True, "color": C_PRIMARY, "spacing": 4}),
        ("    2024 → 2025 共识即有一次更新，固定知识库无法适配", {"size": 13, "color": C_MUTED}),
    ])

    # ---------------- P7 三层流水线 ----------------
    s = d.slide("六、三层构建流水线", "算法创新性（15%）",
                "这是核心方法。先讲整体，再用后面两页讲关键代码。")
    d.flow(s, 2.1, ["L1\n种子本体\n（人工定义 52 类）",
                    "L2\n受约束抽取\n（切分→抽取→对齐）",
                    "L3\n人工审核闭环\n（候选池）"], h=1.5, size=13)
    d.table(s, 0.7, 4.05, 11.9, 2.2, [
        ["层", "做什么", "关键设计"],
        ["L1", "人工定义种子本体（52 类 / 5 关系）", "提供“可对齐的目标”，而非让模型自由发挥"],
        ["L2", "条款切分 → 实体关系抽取 → **强制对齐**", "抽出的概念必须能对齐种子本体，否则不入库"],
        ["L3", "未对齐项进入候选池，人工审核后扩充本体", "本体版本号 +1，重新对齐 —— 这是“可进化”的实现"],
    ], col_w=[0.8, 5.2, 5.9], head_size=14, body_size=12.5)

    # ---------------- P8 关键代码 1 ----------------
    s = d.slide("七、关键代码解读（1/2）：主推荐句 / 注意事项切分",
                "算法创新性（15%）",
                "这是最有技术含量的一段。重点讲“为什么这是个安全性问题”。约 1.5 分钟。")
    d.text(s, 0.7, 1.65, 11.9, 0.75,
           [("问题：条款正文含限定语，若一并抽取会把「随访」条款误读为「建议手术」"
             " —— 即把过度诊疗自动化", {"size": 15, "bold": True, "color": C_ACCENT})])
    d.code(s, 0.7, 2.5, 11.9, 2.55, """# 【推荐意见14】原文：
#   "……如果混杂性结节增大或实性成分增多，通常提示为恶性，
#     需考虑切除，而不是非手术活检……"
# 若从整段抽取，会把 "外科手术根治性切除" 错挂到随访条款上。

CAVEAT_MARKERS = ["随访中需注意", "需注意", "注意事项", "如果", "若"]

def _split_main_and_caveat(text):
    \"\"\"把条款正文拆成「主推荐句」与「注意事项」\"\"\"
    for marker in CAVEAT_MARKERS:
        idx = text.find(marker)
        if idx > 0:
            return text[:idx], text[idx:]   # 主句 / 限定说明
    return text, ""

# 处置动作只从主推荐句抽取；
# 注意事项中的禁忌内容单独抽为 contraindicatedFor 关系。""", size=11.5)
    d.table(s, 0.7, 5.3, 11.9, 1.05, [
        ["条款", "修复前抽出的动作", "修复后"],
        ["推荐意见14", "CT随访、外科手术根治性切除、经验性抗菌治疗、手术活检",
         "CT随访、MDT多学科会诊、检查：CAC、检查：薄层CT"],
    ], col_w=[1.5, 5.4, 5.0], head_size=13, body_size=11.5)

    # ---------------- P9 关键代码 2 ----------------
    s = d.slide("八、关键代码解读（2/2）：否定表述检测", "算法创新性（15%）",
                "这是一个“小改动、大效果”的例子：条款命中率 82.2% → 100%。")
    d.text(s, 0.7, 1.65, 11.9, 0.6,
           [("问题：危险因素抽取只做关键词匹配，不做否定检测 —— "
             "「无吸烟史」会被误判为「有吸烟史」",
             {"size": 15, "bold": True, "color": C_ACCENT})])
    d.code(s, 0.7, 2.35, 11.9, 2.45, """NEGATION_PATTERNS = ["无", "不", "未", "否认", "没有", "非", ...]
GLOBAL_NO_RISK = ["无危险因素", "无吸烟史", "不吸烟", ...]

def _has_negation(text, keyword_pos, window=6):
    \"\"\"在阳性关键词**前方 6 字符窗口**内检测否定词\"\"\"
    start = max(0, keyword_pos - window)
    return any(p in text[start:keyword_pos] for p in NEGATION_PATTERNS)

# 效果：【推荐意见10】（无危险因素）与【推荐意见11】（有危险因素）
#       这两条条款的唯一区别就是“是否存在危险因素”，
#       修复后条款命中率 82.2% → 100.0%""", size=11.5)

    # ---------------- P10 量化效果 ----------------
    s = d.slide("九、量化效果：三份真实指南的跨文档验证", "算法创新性（15%）",
                "强调两点：① 另两份文档未参与本体设计，是干净验证集；"
                "② 人工介入率为 0。")
    d.stat_cards(s, 1.7, [
        ("48,773", "清洗后总字符"),
        ("32", "识别条款"),
        ("186", "对象三元组"),
        ("100%", "本体对齐率"),
        ("0%", "人工介入率"),
    ])
    d.table(s, 0.7, 3.55, 11.9, 2.15, [
        ["文档", "清洗后字符", "条款", "对象三元组", "对齐率"],
        ["肺结节诊治中国专家共识（2024年版）", "19,109", "18", "110", "100%"],
        ["肺癌筛查及肺结节健康管理专家共识（2025版）", "12,056", "13", "37", "100%"],
        ["中国肺癌低剂量CT筛查指南（2023年版）", "9,634", "1", "9", "100%"],
    ], col_w=[6.3, 1.7, 1.1, 1.8, 1.3], head_size=13, body_size=12)
    d.text(s, 0.7, 5.85, 11.9, 0.85, [
        ("★ 本体设计于 2024 共识，却无修改地处理了另两份未参与设计的文档"
         " —— 这是泛化性的直接证据", {"size": 14, "bold": True, "color": C_ACCENT2}),
        ("对比纯人工构建：3.02 小时 → 秒级", {"size": 14, "bold": True, "color": C_ACCENT}),
    ], spacing=3)

    # ---------------- P11 MCP 工具 ----------------
    s = d.slide("十、自研 MCP Server：6 个工具", "编排与 MCP/Skill 集成（15%）",
                "重点讲 kg_consult_decision。约 40 秒。")
    d.table(s, 0.7, 1.75, 11.9, 3.35, [
        ["工具", "职责", "调用时机"],
        ["kg_consult_decision", "★ 核心：多跳推理 + 条款级溯源 + 禁忌判定 + 分级诊疗", "需要完整处置建议时"],
        ["kg_lookup_concept", "概念归一化与定义查询", "术语不确定时"],
        ["kg_get_clause", "条款详情展开（含推荐强度与原文）", "已知条款编号时"],
        ["kg_find_clauses_by_nodule", "按结节特征检索条款", "快速定位 / 覆盖分析"],
        ["kg_get_ontology_summary", "本体概览", "说明知识来源时"],
        ["kg_list_clauses", "条款清单", "确认能力边界时"],
    ], col_w=[3.3, 6.4, 2.6], head_size=13.5, body_size=12.5)
    d.text(s, 0.7, 5.3, 11.9, 0.9,
           [("协议：Streamable HTTP（MCP 2024-11-05） · 端点 http://nexent-mcp:8020/mcp",
             {"size": 13, "color": C_MUTED}),
            ("状态：已接入平台（mcp_record_t）· 6 个工具已挂载到智能体（界面可见）",
             {"size": 13, "color": C_ACCENT2, "bold": True})], spacing=4)

    # ---------------- P12 MCP 协议踩坑 ----------------
    s = d.slide("十一、关键代码：MCP 协议层的真实问题", "编排与 MCP/Skill 集成（15%）",
                "讲这一页是为了说明：我们不只是“调用了 MCP”，而是理解了协议层实现细节。")
    d.text(s, 0.7, 1.65, 11.9, 0.75,
           [("问题：容器间调用 http://nexent-mcp:8020/mcp 时报 HTTP 421 Misdirected Request",
             {"size": 15, "bold": True, "color": C_ACCENT})])
    d.code(s, 0.7, 2.5, 11.9, 2.5, """# 根因：FastMCP 2.x 默认启用 DNS 重绑定保护（DNS rebinding protection），
#       只信任 localhost —— 容器内网调用被拒绝。

from mcp.server.transport_security import TransportSecuritySettings

mcp.settings.transport_security = TransportSecuritySettings(
    enable_dns_rebinding_protection=False,        # 容器内网调用需关闭
    allowed_hosts=[
        "nexent-mcp:8020", "127.0.0.1:8020", "localhost:8020",
    ],
)

# 这是 MCP 协议的安全机制在容器化部署下的适配问题，
# 不是配置错误 —— 理解这一点才能正确定位。""", size=11.5)
    d.text(s, 0.7, 5.25, 11.9, 0.6,
           [("平台机制发现：MCP 工具不会自动登记 —— 注册服务后还需调用 "
             "GET /api/tool/scan_tool 触发扫描",
             {"size": 13.5, "bold": True, "color": C_PRIMARY})])

    # ---------------- P13 Skill 编排 ----------------
    s = d.slide("十二、Skill 三层编排与渐进式披露", "编排与 MCP/Skill 集成（15%）",
                "展示界面证据 —— 智能体主动加载 Skill。这是 Skill 真正生效的证明。")
    d.table(s, 0.7, 1.7, 6.4, 2.3, [
        ["层", "职责", "依赖"],
        ["L1 事实层", "抽取结构化患者事实", "kg_consult_decision"],
        ["L2 推理层", "本体匹配→条款定位→动作展开→禁忌判定", "kg_consult_decision"],
        ["L3 证据层", "回检条款原文", "knowledge_base_search"],
    ], col_w=[1.3, 3.4, 1.7], head_size=13, body_size=11.5)
    d.text(s, 0.7, 4.25, 6.4, 1.9, [
        ("Skill 挂载状态", {"size": 14, "bold": True, "color": C_PRIMARY}),
        ("✅ 已挂载到智能体", {"size": 13, "color": C_ACCENT2, "bold": True}),
        ("skill_instance_id=1", {"size": 11, "color": C_MUTED}),
        ("agent_id=2 · version_no=0 · enabled=true", {"size": 11, "color": C_MUTED}),
        ("", {"size": 6}),
        ("⚠️ 创建 Skill 定义后，还须在 ag_skill_instance_t",
         {"size": 11, "color": C_MUTED}),
        ("    中建立关联，否则界面显示“暂未选择技能”", {"size": 11, "color": C_MUTED}),
    ], spacing=2)
    d.code(s, 7.4, 1.7, 5.2, 4.45, """【界面证据】智能体主动加载 Skill

Reasoning:
  "There's a skill:
   lung-nodule-decision.
   Must load it first."

  此请求与 lung-nodule-decision
  技能描述高度匹配，
  须先加载技能指南。

Executed code (PYTHON):
  skill_content =
      read_skill_md(
        "lung-nodule-decision")
  print(skill_content)

→ 这证明 Nexent 的渐进式
  Skill 披露机制在工作：
  元数据常驻上下文用于匹配，
  命中后才加载完整内容。""", size=11)

    # ---------------- P14 三层拒答 ----------------
    s = d.slide("十三、三层拒答机制 —— 安全设计的核心", "编排与 MCP/Skill 集成（15%）",
                "这是本项目最有说服力的一段：发现问题 → 定位 → 修复 → 量化。约 1.5 分钟。")
    d.table(s, 0.7, 1.7, 11.9, 1.75, [
        ["层", "机制", "实现位置"],
        ["第 1 层 引擎层", "判断 coverage，无匹配条款时返回 NOT_COVERED", "MCP 推理引擎"],
        ["第 2 层 编排层", "提示词强制“缺关键信息必须追问、不给建议”", "Agent 约束提示词"],
        ["第 3 层 表现层", "追问时列出所需信息、给选项、不加免责声明", "输出格式约束"],
    ], col_w=[2.0, 7.2, 2.7], head_size=13, body_size=12)

    d.text(s, 0.7, 3.65, 11.9, 2.6, [
        ("★ 我们发现并修复了一个真实缺陷", {"size": 15, "bold": True, "color": C_ACCENT, "spacing": 6}),
        ("测试问题：“我有肺结节，该怎么办？”（完全缺少结节直径）",
         {"size": 12.5, "color": C_TEXT, "spacing": 4}),
        ("修复前：调用 18 次工具 · 耗时 59 秒 · 输出 2728 字试图硬答",
         {"size": 12.5, "color": C_MUTED, "spacing": 4}),
        ("根因：引擎层有拒答能力，但编排层的提示词里没有“必须追问”这条约束",
         {"size": 12.5, "color": C_MUTED, "spacing": 4}),
        ("修复后：调用 0 次工具 · 耗时 3.5 秒 · 改为结构化追问表单",
         {"size": 13.5, "bold": True, "color": C_ACCENT2, "spacing": 4}),
        ("追问内容：① 结节最大径是多少毫米？（必填）"
         "② 结节密度类型？（单选，含选项）③ 是否存在肺癌危险因素？（多选）",
         {"size": 12, "color": C_TEXT}),
    ], spacing=3)

    # ---------------- P15 知识库与数据处理 ----------------
    s = d.slide("十四、知识库扩展与数据处理", "资产激活的业务价值（15%）",
                "数据处理是官方要求项。重点讲语料清洗的技术难点。")
    d.table(s, 0.7, 1.7, 5.7, 2.6, [
        ["知识库配置"],
        ["名称：肺结节指南知识库"],
        ["存储：Elasticsearch"],
        ["向量模型：BGE-M3（1024 维）"],
        ["分块：17"],
        ["检索：hybrid / accurate / semantic"],
        ["扩展方式：新增文档即自动分块向量化"],
    ], col_w=[1], head_size=13.5, body_size=12)
    d.text(s, 6.9, 1.7, 5.7, 2.6, [
        ("★ 数据处理：语料清洗", {"size": 14, "bold": True, "color": C_ACCENT, "spacing": 6}),
        ("问题：Word 提取的指南含 Zotero 引文元数据", {"size": 12, "spacing": 3}),
        ("ADDIN ZOTERO_ITEM CSL_CITATION {...}", {"size": 10.5, "color": C_MUTED, "spacing": 3}),
        ("2025 共识被污染 230,399 字符，占原文 89%", {"size": 12, "spacing": 3}),
        ("难点：该 JSON 含嵌套括号，正则无法配对", {"size": 12, "spacing": 3}),
        ("解法：括号配对扫描（同时跟踪字符串与转义状态）",
         {"size": 12, "bold": True, "color": C_ACCENT2, "spacing": 3}),
        ("效果：中文占比 8.5% → 72.2%", {"size": 13, "bold": True, "color": C_ACCENT2}),
    ], spacing=2)
    d.text(s, 0.7, 4.6, 11.9, 1.9, [
        ("数据合规（官方要求说明）", {"size": 14, "bold": True, "color": C_PRIMARY, "spacing": 5}),
        ("· 不使用任何真实患者数据 —— 知识来源全部为公开发布的指南与共识",
         {"size": 12.5, "spacing": 3}),
        ("· 评测集由条款适用区间系统化生成，金标准为条款编号本身，可机器判定",
         {"size": 12.5, "spacing": 3}),
        ("· 影像报告样例为按标准格式构造的示例，图中明确标注“不含真实患者信息”",
         {"size": 12.5, "spacing": 3}),
        ("· 数据留存本地服务器，数据不出院", {"size": 12.5}),
    ], spacing=2)

    # ---------------- P16 现场演示 ----------------
    s = d.slide("十五、现场演示（三个场景）", "系统交互体验与能力沉淀（15%）",
                "演示时切到浏览器。三个问题预先放在剪贴板，直接粘贴。"
                "若网络异常则播放录屏。")
    d.table(s, 0.7, 1.8, 11.9, 2.5, [
        ["#", "场景", "演示什么"],
        ["1", "8mm mGGN + 实性成分 2mm + 吸烟 30 年", "双驱动调用序列 · 条款级溯源 · 结构化输出"],
        ["2", "“我有肺结节，该怎么办？”（信息不足）", "★ 交互式追问表单（三层拒答机制）"],
        ["3", "“能否做 PET-CT 评估？”", "条件化禁忌判定：本例实性成分 2mm，属禁忌范围"],
    ], col_w=[0.5, 5.4, 6.0], head_size=13.5, body_size=12.5)
    d.text(s, 0.7, 4.6, 11.9, 1.9, [
        ("演示时请评委关注调试窗口右侧的 Reasoning 面板", {"size": 14, "bold": True, "color": C_PRIMARY, "spacing": 5}),
        ("可以看到智能体：① 判断信息是否充足 → ② 加载 Skill → ③ 调用图谱工具推理 → "
         "④ 回检条款原文 → ⑤ 输出带条款编号的建议",
         {"size": 12.5, "spacing": 4}),
        ("实测指标：典型正例平均 3.4 次工具调用 / 9.8 秒；追问场景 0 次调用 / 3.5 秒",
         {"size": 12.5, "color": C_MUTED}),
    ], spacing=2)

    # ---------------- P17 能力沉淀 ----------------
    s = d.slide("十六、能力沉淀：工作流模板与跨行业迁移", "通用推广价值（15%）",
                "这是“可复用 Skill 工作流模板沉淀方案”的实证。约 40 秒。")
    d.table(s, 0.7, 1.75, 11.9, 1.6, [
        ["领域", "语料性质", "概念", "条款", "对象三元组", "对齐率"],
        ["医疗 · 肺结节规范处置", "真实公开规范（已清洗）", "14", "18", "47", "100%"],
        ["金融 · 信贷风险审查", "样例语料（234 字）", "19", "5", "13", "100%"],
    ], col_w=[3.6, 3.2, 1.2, 1.1, 1.8, 1.3], head_size=13, body_size=12)
    d.text(s, 0.7, 3.5, 11.9, 2.9, [
        ("骨架是否改动：否。仅替换种子本体、领域语料、术语词表、数值模式",
         {"size": 14, "bold": True, "color": C_ACCENT2, "spacing": 6}),
        ("★ 迁移中发现的一个机制：抽取量受种子本体表达力约束",
         {"size": 14, "bold": True, "color": C_PRIMARY, "spacing": 5}),
        ("同一份共识、同样 18 个条款：生产本体（52 类）抽出 110 个三元组，"
         "迁移模板（14 类）抽出 47 个 —— 差异只来自本体的类目粒度",
         {"size": 12.5, "spacing": 4}),
        ("实践含义：迁移时先用小本体打通骨架，再逐步细化；"
         "抽取量的提升应来自本体细化而非抽取算法",
         {"size": 12.5, "color": C_MUTED, "spacing": 6}),
        ("诚实声明：金融领域因无公开的真实信贷审查规范，采用样例语料验证骨架复用性。"
         "我们验证的是流水线的领域无关性，而非声称金融领域已达到医疗领域的验证深度。",
         {"size": 12, "color": C_MUTED, "line_spacing": 1.1}),
    ], spacing=2)

    # ---------------- P18 评测与诚实边界 ----------------
    s = d.slide("十七、自测评测与诚实边界", "系统交互体验与能力沉淀（15%）",
                "这一页体现严谨性。主动讲清“能证明什么、不能证明什么”。")
    d.stat_cards(s, 1.7, [
        ("58", "评测用例"),
        ("100%", "条款命中率"),
        ("100%", "可溯源率"),
        ("100%", "拒答正确率"),
        ("93.1%", "覆盖率"),
    ])
    d.table(s, 0.7, 3.5, 5.75, 3.0, [
        ["本评测能证明"],
        ["条款定位：能否找到正确条款"],
        ["阈值判定：≤ / > 边界是否正确"],
        ["溯源完整性：是否携带条款编号"],
        ["拒答行为：信息不足时是否追问"],
        ["跨文档一致性：四份文档 100% 对齐"],
    ], col_w=[1], head_size=13, body_size=12)
    d.table(s, 6.85, 3.5, 5.75, 3.0, [
        ["本评测不能证明"],
        ["临床有效性 —— 需真实临床数据与伦理审批"],
        ["安全性 —— 需前瞻性研究与不良事件监测"],
        ["真实病例覆盖 —— 用例仍属构造"],
        ["医生决策改善 —— 需对照实验"],
        ["长期稳定性 —— 需持续运行观测"],
    ], col_w=[1], head_size=13, body_size=12)
    d.text(s, 0.7, 6.62, 11.9, 0.5,
           [("这是条款一致性测试，不是临床效果验证",
             {"size": 13, "bold": True, "color": C_ACCENT, "align": PP_ALIGN.CENTER})])

    # ---------------- P19 对照实验（裸模型 vs 本系统）----------------
    s = d.slide("十八、★ 对照实验：裸大模型 vs 本系统",
                "算法创新性（15%）· 通用推广价值（15%）",
                "这是本轮最有说服力的一页。核心不是“我们做了”，而是“不做会怎样”。"
                "约 1 分钟。")
    d.text(s, 0.7, 1.62, 11.9, 0.55,
           [("同一批 6 个临床问题，分别交给两条通路 —— "
             "让评委看差异，而不是听我们自评",
             {"size": 14, "bold": True, "color": C_PRIMARY})])

    d.table(s, 0.7, 2.25, 5.75, 3.75, [
        ["裸大模型（DeepSeek-V3）"],
        ["无知识库 / 无图谱 / 无工具"],
        ["系统提示词仅：“你是呼吸科医生”"],
        ["【推荐意见N】溯源：0 / 6"],
        ["命中中国共识条款：0 / 6"],
        ["分级诊疗 / MDT / CAC：全缺"],
        ["免责声明：0 / 6"],
        ["信息不足时：直接作答"],
        ["引用来源：4 个未标注，1 个引 Fleischner（美国）"],
    ], col_w=[1], head_size=13, body_size=11.5)
    d.table(s, 6.85, 2.25, 5.75, 3.75, [
        ["本系统"],
        ["Nexent + 自研知识图谱 MCP + 知识库"],
        ["完整检索-推理双驱动流程"],
        ["【推荐意见N】溯源：6 / 6"],
        ["命中中国共识条款：6 / 6"],
        ["分级诊疗 / MDT / CAC：均输出"],
        ["免责声明：6 / 6"],
        ["信息不足时：交互式追问表单"],
        ["引用来源：全部标注条款号"],
    ], col_w=[1], head_size=13, body_size=11.5)

    bx = s.shapes.add_shape(1, Inches(0.7), Inches(6.15), Inches(11.9), Inches(1.0))
    bx.fill.solid(); bx.fill.fore_color.rgb = C_LIGHT
    bx.line.color.rgb = C_ACCENT; bx.line.width = Pt(1.25)
    tf = bx.text_frame; tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.text = ("★ 15mm mGGN：裸模型直接建议“胸腔镜手术切除”；"
              "中国共识要求“先 3 个月重复 CT”")
    p.alignment = PP_ALIGN.CENTER
    p.font.size = Pt(13.5); p.font.bold = True
    p.font.color.rgb = C_ACCENT; p.font.name = FONT
    p2 = tf.add_paragraph()
    p2.text = ("而文献显示部分实性结节过度诊断率 31%、亚洲人群 38% —— "
               "两条独立证据指向同一结论")
    p2.alignment = PP_ALIGN.CENTER
    p2.font.size = Pt(11.5); p2.font.color.rgb = C_MUTED; p2.font.name = FONT

    # ---------------- P20 总结 ----------------
    s = d.slide("十九、总结", "通用推广价值（15%）", "收尾 30 秒。不要拖。")
    d.text(s, 0.7, 1.85, 11.9, 3.6, [
        ("我们做了什么", {"size": 20, "bold": True, "color": C_PRIMARY, "spacing": 10}),
        ("把「从行业文档到可执行知识」做成了一条可复制的流水线，"
         "并在肺结节这一个高价值场景中完成了端到端验证。",
         {"size": 16, "spacing": 20}),
        ("三个可复用的产出", {"size": 20, "bold": True, "color": C_PRIMARY, "spacing": 10}),
        ("① 一套本体半自动化构建算法 —— 4 份真实规范 / 100% 对齐 / 人工介入率 0%",
         {"size": 14, "spacing": 5}),
        ("② 一个自研知识图谱 MCP 服务 —— 6 个工具 / 已挂载 / 条款级溯源",
         {"size": 14, "spacing": 5}),
        ("③ 一条领域无关的工作流模板 —— 医疗与金融双领域验证，骨架未改动",
         {"size": 14}),
    ], spacing=8)

    # ---------------- P21 致谢 ----------------
    s = d.slide()
    bg = s.shapes.add_shape(1, Inches(0), Inches(0), SLIDE_W, SLIDE_H)
    bg.fill.solid(); bg.fill.fore_color.rgb = C_PRIMARY; bg.line.fill.background()
    d.text(s, 1.0, 2.6, 11.3, 1.4, "感谢聆听",
           size=44, color=C_WHITE, bold=True, align=PP_ALIGN.CENTER)
    d.text(s, 1.0, 4.1, 11.3, 1.6, [
        "恳请各位评委批评指正",
        "〔学校名称〕 · 〔队伍名称〕",
    ], size=18, color=RGBColor(0xBF, 0xD4, 0xEA), align=PP_ALIGN.CENTER, spacing=14)
    s.notes_slide.notes_text_frame.text = (
        "进入问答环节。参见《国赛答辩框架》第四节的 10 个预设问答。\n"
        "三条原则：有数据就报数据 · 有边界就说边界 · 不会就承认。")

    d.save(out)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="生成国赛答辩 PPT")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    p = build(args.out)
    size = os.path.getsize(p)
    print("=" * 66)
    print("  国赛答辩 PPT 已生成")
    print("=" * 66)
    print(f"  文件: {p}")
    print(f"  大小: {size:,} 字节 ({size/1024:.1f} KB)")
    from pptx import Presentation as P2
    pr = P2(p)
    print(f"  页数: {len(pr.slides)}")
    print(f"  版式: {pr.slide_width.inches:.2f} × {pr.slide_height.inches:.2f} 英寸 (16:9)")
    print("=" * 66)
    return 0


if __name__ == "__main__":
    sys.exit(main())
