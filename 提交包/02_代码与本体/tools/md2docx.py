#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Markdown → Word 转换器（面向比赛提交文档）
================================================================

支撑赛题三初赛材料《开发设计文档》的 DOCX 生成。

支持语法：
    # ~ ####      标题（映射到 Heading 1~4）
    | a | b |     表格（含表头分隔行）
    ```...```     代码块
    - / *         无序列表
    1.            有序列表
    **粗体**      行内粗体
    ---           分隔线
    普通段落

用法：
    python3 md2docx.py --input 文档.md --output 文档.docx --title "标题"
"""

from __future__ import annotations

import argparse
import os
import re
import sys

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor, Cm, Inches


# ---------------------------------------------------------------------------
# 字体设置（中英文分别设置，避免中文显示为方框）
# ---------------------------------------------------------------------------
CN_FONT = "微软雅黑"
EN_FONT = "Calibri"
CODE_FONT = "Consolas"


def set_run_font(run, cn=CN_FONT, en=EN_FONT, size=None,
                 bold=None, color=None):
    run.font.name = en
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = rpr.makeelement(qn("w:rFonts"), {})
        rpr.append(rfonts)
    rfonts.set(qn("w:eastAsia"), cn)
    rfonts.set(qn("w:ascii"), en)
    rfonts.set(qn("w:hAnsi"), en)
    if size is not None:
        run.font.size = Pt(size)
    if bold is not None:
        run.font.bold = bold
    if color is not None:
        run.font.color.rgb = color


def add_inline(par, text: str, size=10.5, base_bold=False):
    """处理行内 **粗体** 与 `代码`。"""
    tokens = re.split(r"(\*\*[^*]+\*\*|`[^`]+`)", text)
    for tk in tokens:
        if not tk:
            continue
        if tk.startswith("**") and tk.endswith("**") and len(tk) > 4:
            r = par.add_run(tk[2:-2])
            set_run_font(r, size=size, bold=True)
        elif tk.startswith("`") and tk.endswith("`") and len(tk) > 2:
            r = par.add_run(tk[1:-1])
            set_run_font(r, cn=CODE_FONT, en=CODE_FONT, size=size - 0.5,
                         color=RGBColor(0xC7, 0x25, 0x4E))
        else:
            r = par.add_run(tk)
            set_run_font(r, size=size, bold=base_bold)


def add_code_block(doc, lines: list[str]):
    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Cm(0.6)
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(6)
    body = "\n".join(lines)
    r = p.add_run(body)
    set_run_font(r, cn=CODE_FONT, en=CODE_FONT, size=9,
                 color=RGBColor(0x1F, 0x3A, 0x5F))
    # 段落底纹
    ppr = p._element.get_or_add_pPr()
    shd = ppr.makeelement(qn("w:shd"), {
        qn("w:val"): "clear", qn("w:color"): "auto", qn("w:fill"): "F5F7FA"})
    ppr.append(shd)
    return p


def add_table(doc, rows: list[list[str]]):
    if not rows:
        return
    ncol = max(len(r) for r in rows)
    t = doc.add_table(rows=0, cols=ncol)
    t.style = "Table Grid"
    for i, row in enumerate(rows):
        cells = t.add_row().cells
        for j in range(ncol):
            txt = row[j] if j < len(row) else ""
            cell = cells[j]
            cell.text = ""
            par = cell.paragraphs[0]
            par.paragraph_format.space_before = Pt(1)
            par.paragraph_format.space_after = Pt(1)
            # 去掉 markdown 表格里的转义竖线
            txt = txt.replace("\\|", "|").strip()
            add_inline(par, txt, size=9.5, base_bold=(i == 0))
    return t


HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
ULIST_RE = re.compile(r"^\s*[-*+]\s+(.*)$")
OLIST_RE = re.compile(r"^\s*(\d+)[.、)]\s+(.*)$")
TABLE_ROW_RE = re.compile(r"^\s*\|(.+)\|\s*$")
TABLE_SEP_RE = re.compile(r"^\s*\|[\s:|-]+\|\s*$")


def add_image(doc, src: str, base_dir: str, caption: str = "") -> bool:
    """插入一张图片（含图注）。

    v1.1 新增：此前 md2docx 不支持 Markdown 图片语法，
    导致生成的 Word **一张图都没有** —— 而初赛材料要求明确列出
    "示例问答截图"作为"Nexent 平台上智能体整体设计思路及详细说明"的组成部分。
    纯材料评审下，界面证据若不内嵌进 Word，评委就看不到。

    支持：
      · 标准 Markdown：`![图注](相对路径)`
      · 相对路径按 md 文件所在目录解析

    返回是否成功插入。
    """
    p = os.path.normpath(os.path.join(base_dir, src))
    if not os.path.exists(p):
        # 找不到图时留一行占位说明，避免静默丢失
        par = doc.add_paragraph()
        r = par.add_run(f"[图片缺失: {src}]")
        r.font.color.rgb = RGBColor(0xC0, 0x39, 0x2B)
        set_run_font(r, size=9)
        return False

    # 单张图最大宽度 16.5cm（A4 正文宽度），等比缩放由 Word 处理
    par = doc.add_paragraph()
    par.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = par.add_run()
    try:
        run.add_picture(p, width=Cm(16.0))
    except Exception as e:                                   # noqa: BLE001
        r2 = par.add_run(f"[图片无法插入: {src} ({type(e).__name__})]")
        set_run_font(r2, size=9)
        return False

    if caption:
        cap = doc.add_paragraph()
        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        cr = cap.add_run(caption)
        set_run_font(cr, size=9)
        cr.font.color.rgb = RGBColor(0x60, 0x60, 0x60)
        cap.paragraph_format.space_after = Pt(8)
    return True


def convert(md_path: str, out_path: str, title: str = "") -> None:
    with open(md_path, encoding="utf-8") as f:
        lines = f.read().split("\n")

    doc = Document()

    # 基础样式
    style = doc.styles["Normal"]
    style.font.name = EN_FONT
    style.font.size = Pt(10.5)
    style.element.rPr.rFonts.set(qn("w:eastAsia"), CN_FONT)

    # 页边距
    for sec in doc.sections:
        sec.top_margin = Cm(2.2)
        sec.bottom_margin = Cm(2.2)
        sec.left_margin = Cm(2.4)
        sec.right_margin = Cm(2.4)

    # 封面标题
    if title:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(title)
        set_run_font(r, size=18, bold=True)
        p.paragraph_format.space_after = Pt(18)

    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        s = line.rstrip()

        # ---- 代码块 ----
        if s.strip().startswith("```"):
            buf = []
            i += 1
            while i < n and not lines[i].strip().startswith("```"):
                buf.append(lines[i])
                i += 1
            add_code_block(doc, buf)
            i += 1
            continue

        # ---- 图片（v1.1 新增）----
        m_img = re.match(r'^\s*!\[([^\]]*)\]\(([^)]+)\)\s*$', s)
        if m_img:
            add_image(doc, m_img.group(2).strip(),
                      os.path.dirname(os.path.abspath(md_path)),
                      m_img.group(1).strip())
            i += 1
            continue

        # ---- 表格 ----
        if TABLE_ROW_RE.match(s):
            block = []
            while i < n and TABLE_ROW_RE.match(lines[i].rstrip()):
                block.append(lines[i].rstrip())
                i += 1
            rows = []
            for b in block:
                if TABLE_SEP_RE.match(b):
                    continue
                inner = b.strip().strip("|")
                cells = inner.split("|")
                rows.append([c.strip() for c in cells])
            add_table(doc, rows)
            doc.add_paragraph().paragraph_format.space_after = Pt(2)
            continue

        # ---- 空行 ----
        if not s.strip():
            i += 1
            continue

        # ---- 分隔线 ----
        if re.match(r"^\s*-{3,}\s*$", s):
            p = doc.add_paragraph()
            ppr = p._element.get_or_add_pPr()
            pbdr = ppr.makeelement(qn("w:pBdr"), {})
            bottom = pbdr.makeelement(qn("w:bottom"), {
                qn("w:val"): "single", qn("w:sz"): "6",
                qn("w:space"): "1", qn("w:color"): "BBBBBB"})
            pbdr.append(bottom)
            ppr.append(pbdr)
            i += 1
            continue

        # ---- 标题 ----
        m = HEADING_RE.match(s)
        if m:
            lvl = min(len(m.group(1)), 4)
            txt = m.group(2).strip()
            h = doc.add_heading(level=lvl)
            h.paragraph_format.space_before = Pt(12 if lvl <= 2 else 8)
            h.paragraph_format.space_after = Pt(6)
            r = h.add_run(re.sub(r"\*\*", "", txt))
            sizes = {1: 16, 2: 13.5, 3: 12, 4: 11}
            set_run_font(r, size=sizes[lvl], bold=True,
                         color=RGBColor(0x1A, 0x1A, 0x1A))
            i += 1
            continue

        # ---- 无序列表 ----
        m = ULIST_RE.match(s)
        if m:
            p = doc.add_paragraph(style="List Bullet")
            p.paragraph_format.space_after = Pt(2)
            add_inline(p, m.group(1), size=10.5)
            i += 1
            continue

        # ---- 有序列表 ----
        m = OLIST_RE.match(s)
        if m:
            p = doc.add_paragraph(style="List Number")
            p.paragraph_format.space_after = Pt(2)
            add_inline(p, m.group(2), size=10.5)
            i += 1
            continue

        # ---- 普通段落 ----
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(4)
        p.paragraph_format.line_spacing = 1.25
        add_inline(p, s.strip(), size=10.5)
        i += 1

    doc.save(out_path)


def main() -> int:
    ap = argparse.ArgumentParser(description="Markdown 转 Word")
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--title", default="")
    args = ap.parse_args()

    if not os.path.exists(args.input):
        print(f"[ERROR] 输入文件不存在: {args.input}", file=sys.stderr)
        return 2
    convert(args.input, args.output, args.title)
    size = os.path.getsize(args.output)
    print(f"✅ 已生成: {args.output}  ({size / 1024:.1f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
