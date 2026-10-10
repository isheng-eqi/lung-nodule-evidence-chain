#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Defense Deck (English) — Huawei ICT Competition, Track 3
================================================================

English version of the China National Final defense deck.

Rationale: the official rules state that presenting in English earns a
**2-point bonus** on the total score. This deck mirrors the Chinese one
slide-for-slide, with terminology kept consistent with the design document.

Usage:
    python3 build_defense_ppt_en.py --out DefenseDeck_EN.pptx
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
# Visual system (identical to the Chinese deck)
# ============================================================================

C_PRIMARY = RGBColor(0x1A, 0x36, 0x5D)
C_ACCENT = RGBColor(0xC0, 0x39, 0x2B)
C_ACCENT2 = RGBColor(0x1F, 0x7A, 0x4D)
C_TEXT = RGBColor(0x2B, 0x2B, 0x2B)
C_MUTED = RGBColor(0x6B, 0x6B, 0x6B)
C_LIGHT = RGBColor(0xF2, 0xF5, 0xF9)
C_WHITE = RGBColor(0xFF, 0xFF, 0xFF)
C_BORDER = RGBColor(0xD5, 0xDD, 0xE5)

FONT = "Calibri"
FONT_BOLD = "Calibri"

SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)


class Deck:
    def __init__(self) -> None:
        self.prs = Presentation()
        self.prs.slide_width = SLIDE_W
        self.prs.slide_height = SLIDE_H
        self.blank = self.prs.slide_layouts[6]
        self.page_no = 0

    def slide(self, title: str = "", rubric: str = "", notes: str = ""):
        s = self.prs.slides.add_slide(self.blank)
        self.page_no += 1
        if title:
            bar = s.shapes.add_shape(1, Inches(0), Inches(0), SLIDE_W, Inches(1.0))
            bar.fill.solid(); bar.fill.fore_color.rgb = C_PRIMARY
            bar.line.fill.background()
            tf = bar.text_frame
            tf.margin_left = Inches(0.55); tf.margin_top = Inches(0.14)
            tf.vertical_anchor = MSO_ANCHOR.MIDDLE
            p = tf.paragraphs[0]; p.text = title
            p.font.size = Pt(26); p.font.bold = True
            p.font.color.rgb = C_WHITE; p.font.name = FONT
        if rubric:
            tag = s.shapes.add_textbox(SLIDE_W - Inches(4.6), Inches(1.06),
                                       Inches(4.3), Inches(0.34))
            tp = tag.text_frame.paragraphs[0]
            tp.text = f"▸ {rubric}"
            tp.alignment = PP_ALIGN.RIGHT
            tp.font.size = Pt(10.5); tp.font.color.rgb = C_MUTED
            tp.font.name = FONT
        pn = s.shapes.add_textbox(SLIDE_W - Inches(1.2), SLIDE_H - Inches(0.45),
                                  Inches(1.0), Inches(0.3))
        pp = pn.text_frame.paragraphs[0]; pp.text = f"{self.page_no}"
        pp.alignment = PP_ALIGN.RIGHT
        pp.font.size = Pt(11); pp.font.color.rgb = C_MUTED
        if notes:
            s.notes_slide.notes_text_frame.text = notes
        return s

    def text(self, s, x, y, w, h, lines, size=16, color=C_TEXT, bold=False,
             align=PP_ALIGN.LEFT, spacing=6.0, line_spacing=1.15):
        box = s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
        tf = box.text_frame; tf.word_wrap = True
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
                cell = tbl.cell(r, c); cell.text = str(data[r][c])
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

    def stat_cards(self, s, y, items, x0=0.7, gap=0.3, total_w=12.0):
        n = len(items)
        cw = (total_w - gap * (n - 1)) / n
        for i, (big, label) in enumerate(items):
            x = x0 + i * (cw + gap)
            card = s.shapes.add_shape(1, Inches(x), Inches(y), Inches(cw), Inches(1.5))
            card.fill.solid(); card.fill.fore_color.rgb = C_LIGHT
            card.line.color.rgb = C_BORDER; card.line.width = Pt(0.75)
            tf = card.text_frame
            tf.margin_top = Inches(0.12); tf.margin_bottom = Inches(0.08)
            tf.vertical_anchor = MSO_ANCHOR.MIDDLE
            p1 = tf.paragraphs[0]; p1.text = str(big)
            p1.alignment = PP_ALIGN.CENTER
            p1.font.size = Pt(26); p1.font.bold = True
            p1.font.color.rgb = C_ACCENT; p1.font.name = FONT
            p2 = tf.add_paragraph(); p2.text = label
            p2.alignment = PP_ALIGN.CENTER
            p2.font.size = Pt(10.5); p2.font.color.rgb = C_MUTED
            p2.font.name = FONT

    def code(self, s, x, y, w, h, code_text, size=11):
        box = s.shapes.add_shape(1, Inches(x), Inches(y), Inches(w), Inches(h))
        box.fill.solid(); box.fill.fore_color.rgb = RGBColor(0xF7, 0xF7, 0xF4)
        box.line.color.rgb = C_BORDER; box.line.width = Pt(0.75)
        tf = box.text_frame; tf.word_wrap = True
        tf.margin_left = Inches(0.14); tf.margin_top = Inches(0.1)
        tf.margin_right = Inches(0.1); tf.margin_bottom = Inches(0.1)
        for i, line in enumerate(code_text.split("\n")):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.text = line; p.space_after = Pt(1); p.line_spacing = 1.0
            for r in p.runs:
                r.font.size = Pt(size); r.font.name = "Consolas"
                r.font.color.rgb = (C_ACCENT2 if line.strip().startswith("#")
                                    else C_TEXT)
        return box

    def flow(self, s, y, steps, x0=0.7, total_w=12.0, h=0.85, size=12):
        n = len(steps); gap = 0.22
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
                ap = ar.text_frame.paragraphs[0]; ap.text = "▶"
                ap.alignment = PP_ALIGN.CENTER
                ap.font.size = Pt(14); ap.font.color.rgb = C_MUTED

    def save(self, path: str) -> str:
        self.prs.save(path)
        return path


# ============================================================================
# Slides
# ============================================================================

def build(out: str) -> str:
    d = Deck()

    # ---- P1 Cover ----
    s = d.slide()
    bg = s.shapes.add_shape(1, Inches(0), Inches(0), SLIDE_W, SLIDE_H)
    bg.fill.solid(); bg.fill.fore_color.rgb = C_PRIMARY; bg.line.fill.background()
    d.text(s, 0.8, 1.7, 11.7, 1.7, "Evidence-Chained Pulmonary Nodule Management",
           size=38, color=C_WHITE, bold=True, align=PP_ALIGN.CENTER)
    d.text(s, 0.8, 3.35, 11.7, 0.9,
           "— Making clinical guidelines executable and auditable at the point of care",
           size=18, color=RGBColor(0xBF, 0xD4, 0xEA), align=PP_ALIGN.CENTER)
    ln = s.shapes.add_shape(1, Inches(5.4), Inches(4.4), Inches(2.5), Pt(2))
    ln.fill.solid(); ln.fill.fore_color.rgb = RGBColor(0x7F, 0xA6, 0xCC)
    ln.line.fill.background()
    d.text(s, 0.8, 4.65, 11.7, 1.5, [
        "Track 3: Building an Evolvable Decision Agent with Huawei ModelEngine Nexent",
        "11th Huawei ICT Competition · China National Final Defense",
        "太原理工大学 · WarrantedBelief",
    ], size=14, color=RGBColor(0xD6, 0xE3, 0xF0), align=PP_ALIGN.CENTER, spacing=9)
    s.notes_slide.notes_text_frame.text = (
        "Opening, 1.5 min. Start with the problem, not the technology.\n"
        "One-line claim: Primary-care physicians do not lack guidelines; "
        "they lack an evidence chain they can follow and cite.")

    # ---- P2 Problem ----
    s = d.slide("1. The Gap Between “Detecting a Nodule” and “Deciding What to Do”",
                "Business Value (15%)",
                "Present the three facts without technical detail. ~1 min.")
    d.table(s, 0.7, 1.75, 11.9, 2.3, [
        ["#", "Fact", "Consequence"],
        ["1", "Imaging AI detects nodules, but output stops at a screening report",
         "It does not answer “what should be done”"],
        ["2", "Guidelines specify what to do, but they are prose written for humans",
         "They cannot be mapped onto an individual report"],
        ["3", "LLMs answer accurately enough, but their answers are not auditable",
         "A physician cannot defend a recommendation with no provenance"],
    ], col_w=[0.5, 6.0, 5.4], head_size=13.5, body_size=12)
    bx = s.shapes.add_shape(1, Inches(0.7), Inches(4.35), Inches(11.9), Inches(1.15))
    bx.fill.solid(); bx.fill.fore_color.rgb = C_LIGHT
    bx.line.color.rgb = C_ACCENT; bx.line.width = Pt(1.25)
    tf = bx.text_frame; tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.text = "Together they form a blind spot: “after detection, before decision”"
    p.alignment = PP_ALIGN.CENTER
    p.font.size = Pt(19); p.font.bold = True
    p.font.color.rgb = C_PRIMARY; p.font.name = FONT
    d.text(s, 0.7, 5.75, 11.9, 0.8,
           [("Our claim: primary-care physicians do not lack guidelines — they lack "
             "an evidence chain they can follow and cite.",
             {"size": 15, "bold": True, "color": C_ACCENT})])

    # ---- P3 Shared gap across industries ----
    s = d.slide("2. This Is Not a Niche Problem — A Shared Structural Gap",
                "Business Value (15%)",
                "Use the analogy to set up the “generalizable value” argument later.")
    d.text(s, 0.7, 1.7, 11.9, 0.5,
           "Four industries share the same document structure: "
           "«clause-based rules + threshold conditions + actions»",
           size=14, color=C_MUTED)
    d.table(s, 0.7, 2.35, 11.9, 2.6, [
        ["Industry", "The same gap"],
        ["Healthcare", "Guidelines say what to do, but a consultation lasts 3 minutes "
                       "and the guideline is 14 pages of prose"],
        ["Finance", "Credit policy is explicit, but a relationship manager cannot "
                    "check every deal clause by clause"],
        ["Manufacturing", "Equipment manuals contain procedures, but operators do not "
                          "open them during a fault"],
        ["Public services", "Service guides are published online, but counter staff still "
                            "rely on experience"],
    ], col_w=[1.9, 10.0], head_size=13.5, body_size=12, first_col_bold=True)
    d.text(s, 0.7, 5.25, 11.9, 0.9,
           [("Our contribution is not “a pulmonary nodule agent”, but a reproducible "
             "pipeline from industry documents to executable knowledge.",
             {"size": 15, "bold": True, "color": C_PRIMARY})])

    # ---- P4 Architecture ----
    s = d.slide("3. Overall Design: Four Layers + Dual Retrieval–Reasoning Drive",
                "Orchestration & MCP/Skill Integration (15%)",
                "Emphasise why we did not rebuild retrieval. ~1 min.")
    d.table(s, 0.7, 1.7, 11.9, 3.2, [
        ["Layer", "Components", "Provided by"],
        ["Application", "Pulmonary nodule management agent (county hospitals, "
                        "community clinics)", "This project"],
        ["Platform", "Agent runtime · knowledge-base retrieval · MCP ecosystem · "
                     "tiered memory", "Nexent"],
        ["Platform", "Domain ontology · knowledge graph · multi-hop reasoning · "
                     "clause-level provenance · 6 MCP tools · Skill orchestration",
         "This project"],
        ["Data", "3 public guidelines + 1 structured table + 1 sample imaging report",
         "Public sources"],
    ], col_w=[1.6, 8.0, 2.3], head_size=13, body_size=11.5)
    bx = s.shapes.add_shape(1, Inches(0.7), Inches(5.15), Inches(11.9), Inches(1.15))
    bx.fill.solid(); bx.fill.fore_color.rgb = C_LIGHT
    bx.line.color.rgb = C_BORDER
    tf = bx.text_frame; tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.text = ("The platform provides retrieval, but not structured domain reasoning.\n"
              "Rather than rebuilding retrieval, we added graph reasoning and "
              "clause-level provenance where the platform had a gap.")
    p.alignment = PP_ALIGN.CENTER
    p.font.size = Pt(14); p.font.color.rgb = C_TEXT; p.font.name = FONT

    # ---- P5 Capability attribution ----
    s = d.slide("4. Capability Attribution: Drawing the Boundary Explicitly",
                "Orchestration & MCP/Skill Integration (15%)",
                "This slide matters — stating what is ours versus the platform's "
                "is more professional than being asked.")
    d.table(s, 0.7, 1.75, 5.7, 3.9, [
        ["Provided by Nexent"],
        ["Agent runtime & orchestration"],
        ["Knowledge-base retrieval (3 modes + rerank)"],
        ["Citation & provenance (knowledge level)"],
        ["MCP tool ecosystem & management"],
        ["Tiered memory"],
        ["Elasticsearch vector retrieval"],
        ["Multimodal model integration"],
    ], col_w=[1], head_size=13.5, body_size=12)
    d.table(s, 6.9, 1.75, 5.7, 3.9, [
        ["Developed in this project"],
        ["Domain ontology (OWL, 57 classes)"],
        ["Knowledge graph (triples + multi-hop)"],
        ["Clause-level provenance & refusal fallback"],
        ["6 MCP tools"],
        ["Skill three-layer orchestration"],
        ["Semi-automated ontology construction"],
        ["Corpus cleaning & data governance"],
    ], col_w=[1], head_size=13.5, body_size=12)
    d.text(s, 0.7, 5.85, 11.9, 0.6,
           [("Platform capability + our increment = dual retrieval–reasoning drive",
             {"size": 15, "bold": True, "color": C_ACCENT2, "align": PP_ALIGN.CENTER})])

    # ---- P6 Challenges ----
    s = d.slide("5. Knowledge Graph Construction: The Low-Resource Challenge",
                "Algorithmic Innovation (15%)", "Challenge first, solution second. ~40 s.")
    d.text(s, 0.7, 1.8, 11.9, 3.6, [
        ("① No public standard ontology exists for this clinical domain",
         {"size": 18, "bold": True, "color": C_PRIMARY, "spacing": 4}),
        ("    General ontologies (e.g. SNOMED) are broad but lack the "
         "“guideline clause” layer", {"size": 12.5, "color": C_MUTED, "spacing": 18}),
        ("② Manual ontology construction is prohibitively expensive",
         {"size": 18, "bold": True, "color": C_PRIMARY, "spacing": 4}),
        ("    At 90 s per triple, a single consensus document takes over 3 hours "
         "of expert time", {"size": 12.5, "color": C_MUTED, "spacing": 18}),
        ("③ Guidelines evolve, so the ontology must evolve too",
         {"size": 18, "bold": True, "color": C_PRIMARY, "spacing": 4}),
        ("    The 2024 → 2025 consensus revision cannot be absorbed by a "
         "static knowledge base", {"size": 12.5, "color": C_MUTED}),
    ])

    # ---- P7 Pipeline ----
    s = d.slide("6. Three-Layer Construction Pipeline", "Algorithmic Innovation (15%)",
                "Core method. Overview here, key code on the next two slides.")
    d.flow(s, 2.1, ["L1\nSeed ontology\n(52 classes, manual)",
                    "L2\nConstrained extraction\n(split → extract → align)",
                    "L3\nHuman review loop\n(candidate pool)"], h=1.5, size=12)
    d.table(s, 0.7, 4.05, 11.9, 2.2, [
        ["Layer", "What it does", "Key design"],
        ["L1", "Manually define the seed ontology (52 classes / 5 relations)",
         "Provides an alignment target instead of letting the model run free"],
        ["L2", "Clause splitting → entity/relation extraction → forced alignment",
         "Extracted concepts must align to the seed ontology, otherwise discarded"],
        ["L3", "Unaligned items enter a candidate pool for human review",
         "Ontology version +1 then realign — this is how “evolvable” is realised"],
    ], col_w=[0.8, 5.2, 5.9], head_size=13, body_size=12)

    # ---- P8 Key code 1 ----
    s = d.slide("7. Key Code (1/2): Splitting Main Recommendation from Caveats",
                "Algorithmic Innovation (15%)",
                "The most substantive piece. Frame it as a safety issue, not a "
                "parsing trick. ~1.5 min.")
    d.text(s, 0.7, 1.62, 11.9, 0.75,
           [("Problem: clauses contain qualifiers. Extracting the whole paragraph "
             "attaches “surgical resection” to a follow-up clause — automating "
             "overtreatment.",
             {"size": 13.5, "bold": True, "color": C_ACCENT})])
    d.code(s, 0.7, 2.45, 11.9, 2.6, """# Recommendation 14 (verbatim):
#   "...if the mixed nodule enlarges or its solid component increases,
#    malignancy is likely: consider RESECTION rather than non-surgical biopsy."
# Extracting the whole paragraph wrongly attaches "surgical resection"
# to the follow-up clause.

CAVEAT_MARKERS = ["follow-up note", "note that", "caution", "if", "when"]

def _split_main_and_caveat(text):
    \"\"\"Split a clause into its main recommendation and its caveats.\"\"\"
    for marker in CAVEAT_MARKERS:
        idx = text.find(marker)
        if idx > 0:
            return text[:idx], text[idx:]      # main sentence / qualifier
    return text, ""

# Actions are extracted ONLY from the main sentence.
# Contraindications inside caveats are extracted separately
# as `contraindicatedFor` relations.""", size=10.5)
    d.table(s, 0.7, 5.25, 11.9, 1.1, [
        ["Clause", "Actions extracted BEFORE", "AFTER"],
        ["Rec. 14", "CT follow-up, surgical resection, empirical antibiotics, surgical biopsy",
         "CT follow-up, MDT consultation, CAC test, thin-slice CT"],
    ], col_w=[1.2, 5.7, 5.0], head_size=12.5, body_size=11)

    # ---- P9 Key code 2 ----
    s = d.slide("8. Key Code (2/2): Negation Detection", "Algorithmic Innovation (15%)",
                "A small change with a large effect: clause hit rate 82.2% → 100%.")
    d.text(s, 0.7, 1.62, 11.9, 0.7,
           [("Problem: risk-factor extraction was pure keyword matching. "
             "“no smoking history” was counted as “smoking history”.",
             {"size": 13.5, "bold": True, "color": C_ACCENT})])
    d.code(s, 0.7, 2.45, 11.9, 2.5, """NEGATION_PATTERNS = ["no", "not", "never", "denies", "without", "non-", ...]
GLOBAL_NO_RISK    = ["no risk factors", "no smoking history", "non-smoker", ...]

def _has_negation(text, keyword_pos, window=6):
    \"\"\"Look for a negation within a 6-character window BEFORE the keyword.\"\"\"
    start = max(0, keyword_pos - window)
    return any(p in text[start:keyword_pos] for p in NEGATION_PATTERNS)

# Effect: Recommendation 10 (no risk factors) and Recommendation 11
#         (with risk factors) differ ONLY by risk-factor presence.
#         After the fix: clause hit rate 82.2% → 100.0%""", size=10.5)

    # ---- P10 Quantitative results ----
    s = d.slide("9. Quantitative Results: Cross-Document Validation on 3 Real Guidelines",
                "Algorithmic Innovation (15%)",
                "Two points: (1) the other two documents were never used to design "
                "the ontology — a clean hold-out; (2) human intervention rate is 0%.")
    d.stat_cards(s, 1.7, [
        ("48,773", "characters (cleaned)"),
        ("32", "clauses found"),
        ("186", "object triples"),
        ("100%", "ontology alignment"),
        ("0%", "human intervention"),
    ])
    d.table(s, 0.7, 3.55, 11.9, 2.15, [
        ["Document", "Chars (cleaned)", "Clauses", "Object triples", "Alignment"],
        ["Chinese Expert Consensus on Pulmonary Nodule Management (2024)",
         "19,109", "18", "110", "100%"],
        ["Expert Consensus on Lung Cancer Screening & Nodule Health Management (2025)",
         "12,056", "13", "37", "100%"],
        ["Chinese Guideline for Low-Dose CT Lung Cancer Screening (2023)",
         "9,634", "1", "9", "100%"],
    ], col_w=[6.5, 1.6, 1.1, 1.7, 1.3], head_size=12, body_size=11)
    d.text(s, 0.7, 5.85, 11.9, 0.9, [
        ("★ The ontology was designed on the 2024 consensus, yet processed the other "
         "two documents without modification — direct evidence of generalisation.",
         {"size": 13, "bold": True, "color": C_ACCENT2}),
        ("Versus fully manual construction: 3.02 hours → seconds",
         {"size": 13, "bold": True, "color": C_ACCENT}),
    ], spacing=3)

    # ---- P11 MCP tools ----
    s = d.slide("10. Our Own MCP Server: 6 Tools", "Orchestration & MCP/Skill Integration (15%)",
                "Focus on kg_consult_decision. ~40 s.")
    d.table(s, 0.7, 1.75, 11.9, 3.35, [
        ["Tool", "Responsibility", "When it is called"],
        ["kg_consult_decision", "★ Core: multi-hop reasoning + clause-level provenance "
                               "+ contraindication + referral tier",
         "When a full recommendation is needed"],
        ["kg_lookup_concept", "Concept normalisation and definition lookup",
         "When terminology is uncertain"],
        ["kg_get_clause", "Expand a clause (strength + full text)",
         "When the clause number is known"],
        ["kg_find_clauses_by_nodule", "Retrieve clauses by nodule features",
         "Fast lookup / coverage analysis"],
        ["kg_get_ontology_summary", "Ontology overview", "When explaining knowledge sources"],
        ["kg_list_clauses", "List all clauses", "To state capability boundaries"],
    ], col_w=[3.2, 6.3, 2.8], head_size=12.5, body_size=11.5)
    d.text(s, 0.7, 5.3, 11.9, 0.9,
           [("Protocol: Streamable HTTP (MCP 2024-11-05) · Endpoint http://nexent-mcp:8020/mcp",
             {"size": 12.5, "color": C_MUTED}),
            ("Status: registered on the platform · all 6 tools mounted on the agent "
             "(visible in the UI)", {"size": 12.5, "color": C_ACCENT2, "bold": True})],
           spacing=4)

    # ---- P12 MCP protocol issue ----
    s = d.slide("11. Key Code: A Real Problem at the MCP Protocol Layer",
                "Orchestration & MCP/Skill Integration (15%)",
                "This slide shows we did not merely “call MCP” — we understood "
                "the protocol implementation.")
    d.text(s, 0.7, 1.62, 11.9, 0.75,
           [("Problem: calling http://nexent-mcp:8020/mcp between containers "
             "returned HTTP 421 Misdirected Request",
             {"size": 13.5, "bold": True, "color": C_ACCENT})])
    d.code(s, 0.7, 2.45, 11.9, 2.6, """# Root cause: FastMCP 2.x enables DNS-rebinding protection by default,
#             trusting only localhost — so intra-container calls were rejected.

from mcp.server.transport_security import TransportSecuritySettings

mcp.settings.transport_security = TransportSecuritySettings(
    enable_dns_rebinding_protection=False,     # required for container networking
    allowed_hosts=[
        "nexent-mcp:8020", "127.0.0.1:8020", "localhost:8020",
    ],
)

# This is the MCP security mechanism meeting containerised deployment,
# not a misconfiguration — understanding that is what makes it fixable.""", size=10.5)
    d.text(s, 0.7, 5.3, 11.9, 0.75,
           [("Platform mechanism discovered: MCP tools are NOT registered "
             "automatically after adding the server — you must call "
             "GET /api/tool/scan_tool to trigger a scan.",
             {"size": 12.5, "bold": True, "color": C_PRIMARY})])

    # ---- P13 Skill orchestration ----
    s = d.slide("12. Skill: Three-Layer Orchestration and Progressive Disclosure",
                "Orchestration & MCP/Skill Integration (15%)",
                "Show the UI evidence — the agent loads the Skill on its own. "
                "That is what proves the Skill is actually in effect.")
    d.table(s, 0.7, 1.7, 6.4, 2.3, [
        ["Layer", "Responsibility", "Depends on"],
        ["L1 Facts", "Extract structured patient facts", "kg_consult_decision"],
        ["L2 Reasoning", "Ontology match → clause location → action expansion "
                         "→ contraindication", "kg_consult_decision"],
        ["L3 Evidence", "Re-check the original clause text", "knowledge_base_search"],
    ], col_w=[1.4, 3.3, 1.7], head_size=12.5, body_size=11)
    d.text(s, 0.7, 4.25, 6.4, 1.95, [
        ("Skill mount status", {"size": 13.5, "bold": True, "color": C_PRIMARY}),
        ("✅ Mounted on the agent", {"size": 12.5, "color": C_ACCENT2, "bold": True}),
        ("skill_instance_id=1", {"size": 10.5, "color": C_MUTED}),
        ("agent_id=2 · version_no=0 · enabled=true", {"size": 10.5, "color": C_MUTED}),
        ("", {"size": 6}),
        ("⚠️ Defining a Skill is not enough — you must also create a row in",
         {"size": 10.5, "color": C_MUTED}),
        ("    ag_skill_instance_t linking it to the agent, otherwise",
         {"size": 10.5, "color": C_MUTED}),
        ("    the UI shows “no skill selected”.", {"size": 10.5, "color": C_MUTED}),
    ], spacing=2)
    d.code(s, 7.4, 1.7, 5.2, 4.5, """【UI EVIDENCE】The agent loads the Skill itself

Reasoning:
  "There's a skill:
   lung-nodule-decision.
   Must load it first."

  This request matches the
  lung-nodule-decision skill
  description — the skill guide
  must be loaded first.

Executed code (PYTHON):
  skill_content =
      read_skill_md(
        "lung-nodule-decision")
  print(skill_content)

→ This shows Nexent's progressive
  skill disclosure at work:
  metadata stays in context for
  matching; full content is loaded
  only on a hit.""", size=10.5)

    # ---- P14 Refusal mechanism ----
    s = d.slide("13. Three-Layer Refusal Mechanism — The Safety Core",
                "Orchestration & MCP/Skill Integration (15%)",
                "Our strongest narrative: found → located → fixed → quantified. "
                "~1.5 min.")
    d.table(s, 0.7, 1.7, 11.9, 1.75, [
        ["Layer", "Mechanism", "Implemented in"],
        ["1. Engine", "Evaluate coverage; return NOT_COVERED when no clause matches",
         "MCP reasoning engine"],
        ["2. Orchestration", "Prompt enforces “ask first when key facts are missing; "
                             "give no advice”", "Agent constraint prompt"],
        ["3. Presentation", "The clarification lists required fields, offers options, "
                            "omits the disclaimer", "Output format constraints"],
    ], col_w=[1.9, 7.3, 2.7], head_size=12.5, body_size=11.5)
    d.text(s, 0.7, 3.65, 11.9, 2.7, [
        ("★ We found and fixed a real defect", {"size": 14, "bold": True,
                                                "color": C_ACCENT, "spacing": 6}),
        ("Test question: “I have a pulmonary nodule, what should I do?” "
         "(no nodule diameter given)", {"size": 12, "spacing": 4}),
        ("Before: 18 tool calls · 59 s · 2,728 characters attempting an answer anyway",
         {"size": 12, "color": C_MUTED, "spacing": 4}),
        ("Root cause: the engine could refuse, but the orchestration prompt contained "
         "no “must ask first” constraint", {"size": 12, "color": C_MUTED, "spacing": 4}),
        ("After: 0 tool calls · 3.5 s · replaced by a structured clarification form",
         {"size": 12.5, "bold": True, "color": C_ACCENT2, "spacing": 4}),
        ("The form asks: ① maximum diameter in mm (required) "
         "② density type (single choice) ③ risk factors (multiple choice)",
         {"size": 11.5, "color": C_TEXT}),
    ], spacing=3)

    # ---- P15 Knowledge base & data processing ----
    s = d.slide("14. Knowledge Base Expansion and Data Processing",
                "Business Value of Asset Activation (15%)",
                "Data processing is an official requirement. Highlight the corpus "
                "cleaning technique.")
    d.table(s, 0.7, 1.7, 5.7, 2.6, [
        ["Knowledge base"],
        ["Name: Pulmonary Nodule Guideline KB"],
        ["Store: Elasticsearch"],
        ["Embedding: BGE-M3 (1024-dim)"],
        ["Chunks: 17"],
        ["Modes: hybrid / accurate / semantic"],
        ["Expansion: upload a document → auto-chunked and vectorised"],
    ], col_w=[1], head_size=12.5, body_size=11.5)
    d.text(s, 6.9, 1.7, 5.7, 2.6, [
        ("★ Data processing: corpus cleaning", {"size": 13.5, "bold": True,
                                                "color": C_ACCENT, "spacing": 6}),
        ("Problem: Word-extracted guidelines contain Zotero citation metadata",
         {"size": 11.5, "spacing": 3}),
        ("ADDIN ZOTERO_ITEM CSL_CITATION {...}", {"size": 10, "color": C_MUTED, "spacing": 3}),
        ("89% of the 2025 consensus (230,399 chars) was polluted",
         {"size": 11.5, "spacing": 3}),
        ("Difficulty: the JSON has nested braces — regex cannot pair them",
         {"size": 11.5, "spacing": 3}),
        ("Solution: brace-matching scan (tracking string/escape state)",
         {"size": 11.5, "bold": True, "color": C_ACCENT2, "spacing": 3}),
        ("Effect: Chinese-character ratio 8.5% → 72.2%",
         {"size": 12, "bold": True, "color": C_ACCENT2}),
    ], spacing=2)
    d.text(s, 0.7, 4.6, 11.9, 1.95, [
        ("Data compliance", {"size": 13.5, "bold": True, "color": C_PRIMARY, "spacing": 5}),
        ("· No real patient data is used — all knowledge comes from published "
         "guidelines and expert consensus", {"size": 12, "spacing": 3}),
        ("· The evaluation set is generated systematically from clause applicability "
         "ranges; the gold standard is the clause number itself, machine-checkable",
         {"size": 12, "spacing": 3}),
        ("· The sample imaging report is constructed to a standard format and is "
         "labelled “contains no real patient information”", {"size": 12, "spacing": 3}),
        ("· Data stays on a local server and never leaves the institution",
         {"size": 12}),
    ], spacing=2)

    # ---- P16 Live demo ----
    s = d.slide("15. Live Demonstration (Three Scenarios)",
                "Interaction Experience & Capability Accumulation (15%)",
                "Switch to the browser. Pre-load the three questions into the "
                "clipboard. Fall back to the recording if the network misbehaves.")
    d.table(s, 0.7, 1.8, 11.9, 2.5, [
        ["#", "Scenario", "What it demonstrates"],
        ["1", "8 mm mGGN + 2 mm solid component + 30-year smoking history",
         "Dual-drive call sequence · clause-level provenance · structured output"],
        ["2", "“I have a pulmonary nodule, what should I do?” (insufficient info)",
         "★ Interactive clarification form (three-layer refusal mechanism)"],
        ["3", "“Can PET-CT be used for assessment?”",
         "Conditional contraindication: solid component 2 mm → within the "
         "contraindicated range"],
    ], col_w=[0.5, 5.4, 6.0], head_size=12.5, body_size=11.5)
    d.text(s, 0.7, 4.6, 11.9, 1.95, [
        ("Please watch the Reasoning panel on the right of the debug window",
         {"size": 13.5, "bold": True, "color": C_PRIMARY, "spacing": 5}),
        ("You will see the agent: ① check whether the facts suffice → ② load the Skill "
         "→ ③ call graph tools to reason → ④ re-check the clause text → "
         "⑤ answer with clause numbers", {"size": 12, "spacing": 4}),
        ("Measured: typical case 3.4 tool calls / 9.8 s; clarification case "
         "0 calls / 3.5 s", {"size": 12, "color": C_MUTED}),
    ], spacing=2)

    # ---- P17 Capability accumulation ----
    s = d.slide("16. Capability Accumulation: Workflow Template and Cross-Industry Migration",
                "Generalizable Value (15%)",
                "This is the evidence for “reusable Skill workflow template”. ~40 s.")
    d.table(s, 0.7, 1.75, 11.9, 1.6, [
        ["Domain", "Corpus", "Concepts", "Clauses", "Object triples", "Alignment"],
        ["Healthcare · pulmonary nodule management", "Real public guideline (cleaned)",
         "14", "18", "47", "100%"],
        ["Finance · credit risk review", "Sample corpus (234 chars)", "19", "5", "13", "100%"],
    ], col_w=[3.9, 3.1, 1.2, 1.1, 1.8, 1.3], head_size=12, body_size=11)
    d.text(s, 0.7, 3.5, 11.9, 2.9, [
        ("Skeleton changed: no. Only the seed ontology, corpus, term lexicon and "
         "numeric patterns were replaced.", {"size": 13, "bold": True, "color": C_ACCENT2,
                                             "spacing": 6}),
        ("★ A mechanism discovered during migration: extraction volume is bounded by "
         "seed-ontology expressiveness", {"size": 13, "bold": True, "color": C_PRIMARY,
                                          "spacing": 5}),
        ("Same consensus, same 18 clauses: the production ontology (52 classes) yields "
         "110 triples; the migration template (14 classes) yields 47 — the difference "
         "comes only from ontology granularity.", {"size": 12, "spacing": 4}),
        ("Practical implication: start migration with a compact ontology to get the "
         "skeleton working, then refine; gains in extraction volume should come from "
         "ontology refinement, not from the extraction algorithm.",
         {"size": 12, "color": C_MUTED, "spacing": 6}),
        ("Honest disclosure: no public credit-review standard exists, so the finance "
         "domain uses a sample corpus. We validate the pipeline's domain-independence, "
         "not that finance reaches the same validation depth as healthcare.",
         {"size": 11.5, "color": C_MUTED, "line_spacing": 1.1}),
    ], spacing=2)

    # ---- P18 Evaluation & honest boundary ----
    s = d.slide("17. Self-Evaluation and Honest Boundaries",
                "Interaction Experience & Capability Accumulation (15%)",
                "This slide demonstrates rigour: state what can and cannot be proven.")
    d.stat_cards(s, 1.7, [
        ("68", "test cases"),
        ("100%", "clause hit rate"),
        ("100%", "traceability"),
        ("100%", "refusal accuracy"),
        ("93.1%", "coverage"),
    ])
    d.table(s, 0.7, 3.5, 5.75, 3.0, [
        ["What this evaluation proves"],
        ["Clause location: the correct clause is found"],
        ["Threshold decisions: ≤ / > boundaries are right"],
        ["Traceability: every answer cites clause numbers"],
        ["Refusal behaviour: clarification when facts are missing"],
        ["Cross-document consistency: 3 documents, 100% aligned"],
    ], col_w=[1], head_size=12.5, body_size=11.5)
    d.table(s, 6.85, 3.5, 5.75, 3.0, [
        ["What it does NOT prove"],
        ["Clinical effectiveness — needs real data and ethics approval"],
        ["Safety — needs prospective studies and adverse-event monitoring"],
        ["Real-case coverage — cases are still constructed"],
        ["Improved physician decisions — needs a controlled trial"],
        ["Long-term stability — needs sustained operation"],
    ], col_w=[1], head_size=12.5, body_size=11.5)
    d.text(s, 0.7, 6.62, 11.9, 0.5,
           [("This is a clause-consistency test, not a clinical-effectiveness trial",
             {"size": 12.5, "bold": True, "color": C_ACCENT, "align": PP_ALIGN.CENTER})])

    # ---- P19 Controlled comparison: bare LLM vs our system ----
    s = d.slide("18. ★ Controlled Comparison: Bare LLM vs Our System",
                "Algorithmic Innovation (15%) · Generalizable Value (15%)",
                "Our strongest slide. The point is not “what we built” but "
                "“what happens without it”. ~1 min.")
    d.text(s, 0.7, 1.62, 11.9, 0.55,
           [("The same six clinical questions, routed two ways — let the judges "
             "see the difference instead of hearing us self-assess.",
             {"size": 14, "bold": True, "color": C_PRIMARY})])
    d.table(s, 0.7, 2.25, 5.75, 3.75, [
        ["Bare LLM (DeepSeek-V3)"],
        ["No knowledge base / no graph / no tools"],
        ["System prompt: “You are a respiratory physician”"],
        ["Clause-level citations: 0 / 6"],
        ["Expected Chinese-consensus clause: 0 / 6"],
        ["Tiered referral / MDT / CAC: all absent"],
        ["Disclaimer: 0 / 6"],
        ["Insufficient information: answers anyway"],
        ["Sources: 4 unlabelled, 1 cites Fleischner (US)"],
    ], col_w=[1], head_size=12.5, body_size=11)
    d.table(s, 6.85, 2.25, 5.75, 3.75, [
        ["Our system"],
        ["Nexent + our knowledge-graph MCP + KB"],
        ["Full dual retrieval–reasoning flow"],
        ["Clause-level citations: 6 / 6"],
        ["Expected Chinese-consensus clause: 6 / 6"],
        ["Tiered referral / MDT / CAC: all present"],
        ["Disclaimer: 6 / 6"],
        ["Insufficient information: clarification form"],
        ["Sources: every claim carries a clause number"],
    ], col_w=[1], head_size=12.5, body_size=11)
    bx = s.shapes.add_shape(1, Inches(0.7), Inches(6.15), Inches(11.9), Inches(1.0))
    bx.fill.solid(); bx.fill.fore_color.rgb = C_LIGHT
    bx.line.color.rgb = C_ACCENT; bx.line.width = Pt(1.25)
    tf = bx.text_frame; tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.text = ("★ 15 mm mGGN: the bare LLM recommends “thoracoscopic resection”; "
              "the Chinese consensus requires “repeat CT at 3 months” first")
    p.alignment = PP_ALIGN.CENTER
    p.font.size = Pt(13); p.font.bold = True
    p.font.color.rgb = C_ACCENT; p.font.name = FONT
    p2 = tf.add_paragraph()
    p2.text = ("Literature reports 31% overdiagnosis for part-solid nodules and 38% "
               "in Asian populations — two independent lines of evidence agree")
    p2.alignment = PP_ALIGN.CENTER
    p2.font.size = Pt(11); p2.font.color.rgb = C_MUTED; p2.font.name = FONT

    # ---- P20 Summary ----
    s = d.slide("19. Summary", "Generalizable Value (15%)", "Closing, 30 s. Do not drag.")
    d.text(s, 0.7, 1.85, 11.9, 3.6, [
        ("What we built", {"size": 19, "bold": True, "color": C_PRIMARY, "spacing": 10}),
        ("A reproducible pipeline from industry documents to executable knowledge, "
         "validated end-to-end in one high-value scenario: pulmonary nodule management.",
         {"size": 15, "spacing": 20}),
        ("Three reusable outputs", {"size": 19, "bold": True, "color": C_PRIMARY,
                                    "spacing": 10}),
        ("① A semi-automated ontology construction algorithm — 3 real guidelines / "
         "100% alignment / 0% human intervention", {"size": 13, "spacing": 5}),
        ("② A self-developed knowledge-graph MCP service — 6 tools / mounted / "
         "clause-level provenance", {"size": 13, "spacing": 5}),
        ("③ A domain-agnostic workflow template — validated in healthcare and finance "
         "without changing the skeleton", {"size": 13}),
    ], spacing=8)

    # ---- P20 Thanks ----
    s = d.slide()
    bg = s.shapes.add_shape(1, Inches(0), Inches(0), SLIDE_W, SLIDE_H)
    bg.fill.solid(); bg.fill.fore_color.rgb = C_PRIMARY; bg.line.fill.background()
    d.text(s, 1.0, 2.6, 11.3, 1.4, "Thank You",
           size=44, color=C_WHITE, bold=True, align=PP_ALIGN.CENTER)
    d.text(s, 1.0, 4.1, 11.3, 1.6, [
        "We welcome your questions and comments",
        "太原理工大学 · WarrantedBelief",
    ], size=17, color=RGBColor(0xBF, 0xD4, 0xEA), align=PP_ALIGN.CENTER, spacing=14)
    s.notes_slide.notes_text_frame.text = (
        "Enter Q&A. See Section 4 of the defense framework for 10 prepared answers.\n"
        "Three principles: quote data when you have it · state boundaries when they "
        "exist · admit when you do not know.")

    d.save(out)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the English defense deck")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    p = build(args.out)
    size = os.path.getsize(p)
    pr = Presentation(p)
    print("=" * 66)
    print("  English Defense Deck generated")
    print("=" * 66)
    print(f"  File    : {p}")
    print(f"  Size    : {size:,} bytes ({size/1024:.1f} KB)")
    print(f"  Slides  : {len(pr.slides)}")
    print(f"  Format  : {pr.slide_width.inches:.2f} x {pr.slide_height.inches:.2f} in (16:9)")
    print("=" * 66)
    return 0


if __name__ == "__main__":
    sys.exit(main())
