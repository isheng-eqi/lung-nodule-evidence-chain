#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
领域语料清洗器
================================================================

对应赛题要求中的"数据处理说明"环节。

背景：从 Word/PDF 提取的指南全文常混入非正文内容，直接用于知识抽取会导致：

  1. **Zotero/Mendeley 引文元数据**：Word 插件插入的
     `ADDIN ZOTERO_ITEM CSL_CITATION {...}` JSON 块，
     在 2025 版共识中占总字符数的 **91%**
  2. **页眉页脚**：期刊名、卷期号、页码、英文刊名
  3. **参考文献列表**：正文之后的英文条目
  4. **不可见控制字符**：软连字符、零宽字符等

本清洗器按以下步骤处理：

    原文 → ① 去引文元数据 → ② 去页眉页脚 → ③ 去参考文献
         → ④ 规范化空白 → ⑤ 质量校验 → 干净语料

用法：
    python3 clean_corpus.py --input raw.txt --out clean.txt --report
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field, asdict


# ============================================================================
# 清洗规则
# ============================================================================

# ① Zotero / Mendeley 引文元数据
# 注意：这些字段名的大小写必须精确匹配，避免误删正文中的普通单词。
CITATION_PATTERNS = [
    # Zotero Word 插件：ADDIN ZOTERO_ITEM CSL_CITATION {...}
    re.compile(r"ADDIN\s+ZOTERO_ITEM\s+CSL_CITATION\s*\{.*?\}\s*(?=ADDIN|\Z)",
               re.DOTALL),
    re.compile(r"ADDIN\s+ZOTERO_BIBL\s*\{.*?\}\s*(?=ADDIN|\Z)", re.DOTALL),
    re.compile(r"ADDIN\s+CSL_BIBLIOGRAPHY\s*\{.*?\}\s*(?=ADDIN|\Z)", re.DOTALL),
    re.compile(r"ADDIN\s+ZOTERO_ITEM\s*\{.*?\}\s*(?=ADDIN|\Z)", re.DOTALL),
    # 通用兜底：ADDIN + 大写标识符 + 可选 JSON
    re.compile(r"ADDIN\s+[A-Z][A-Z0-9_.]*\s*(?:\{.*?\})?\s*(?=ADDIN|\Z)",
               re.DOTALL),
    # 行尾残留的独立 ADDIN 标记
    re.compile(r"\s*ADDIN\s+(?=【|\[|\n|$)"),
    re.compile(r"\s*ADDIN\s*$", re.MULTILINE),
    # Mendeley
    re.compile(r"ADDIN\s+EN\.CITATION.*?(?=\n|$)", re.DOTALL),
]

# ② 页眉页脚特征
HEADER_PATTERNS = [
    re.compile(r"^\s*中国肺癌杂志.*$", re.MULTILINE),
    re.compile(r"^\s*Chin\s+J\s+Lung\s+Cancer.*$", re.MULTILINE),
    re.compile(r"^\s*·\s*专家共识\s*·\s*$", re.MULTILINE),
    re.compile(r"^\s*中华\S+杂志.*第\s*\d+\s*卷.*$", re.MULTILINE),
    re.compile(r"^\s*DOI:\s*10\.\S+\s*$", re.MULTILINE),
    re.compile(r"^\s*[·•]\s*\d+\s*[·•]\s*$", re.MULTILINE),
    # 纯英文行（无中文且较长）—— 页眉与英文参考文献条目
    re.compile(r"^\s*[A-Za-z][A-Za-z\s,\.\-\(\)\[\]:;'’/&0-9]{40,}\s*$", re.MULTILINE),
    # 邮箱/超链接残留
    re.compile(r"HYPERLINK\s+\"mailto:[^\"]*\"\s*", re.IGNORECASE),
    re.compile(r"\S+@\S+\.\S+", re.IGNORECASE),
    # 执笔老师联系方式（含电话号码）
    re.compile(r"（执笔老师[：:][^）]*）", re.MULTILINE),
    # Zotero 参考文献区标记行
    re.compile(r"^.*CSL_BIBLIOGRAPHY.*$", re.MULTILINE),
    # 编号英文参考文献条目（逐行删除，不截断文档）
    re.compile(r"^\s*\[\d+\]\s*[A-Za-z][^\n]*$", re.MULTILINE),
    # 网页页脚：版权、ICP 备案、公安备案声明
    re.compile(r"^.*Copyright\s*©.*$", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^.*版权所有.*$", re.MULTILINE),
    re.compile(r"^.*京ICP备\S*.*$", re.MULTILINE),
    re.compile(r"^.*京公网安备\S*.*$", re.MULTILINE),
    re.compile(r"^.*All\s+Rights?\s+Reserved.*$", re.MULTILINE | re.IGNORECASE),
    # 站点导航残留
    re.compile(r"^.*(医脉通|丁香园|用药助手|指南网|注册与透明化平台).{0,40}$", re.MULTILINE),
]

# ③ 参考文献区起始标记（仅在文档后半段才截断）
REFERENCE_MARKERS = [
    re.compile(r"^\s*参\s*考\s*文\s*献\s*$", re.MULTILINE),
    re.compile(r"^\s*References\s*$", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^\s*【?\s*参考\s*文献\s*】?\s*$", re.MULTILINE),
]

# ④ 不可见字符
INVISIBLE = re.compile(r"[\u00ad\u200b-\u200f\u2028-\u202f\ufeff\ufff9-\ufffb]")


@dataclass
class CleanReport:
    """清洗报告。"""
    src: str = ""
    raw_chars: int = 0
    raw_cjk: int = 0
    clean_chars: int = 0
    clean_cjk: int = 0
    removed_citation_chars: int = 0
    removed_header_chars: int = 0
    removed_reference_chars: int = 0
    removed_invisible: int = 0
    citation_blocks: int = 0
    quality_before: float = 0.0     # 中文占比
    quality_after: float = 0.0
    verdict: str = ""
    notes: list[str] = field(default_factory=list)


def _strip_balanced_json(text: str, anchor: str) -> tuple[str, int]:
    """删除 `anchor` 之后紧跟的、括号配对完整的 JSON 对象。

    Zotero 引文字段形如：
        ADDIN ZOTERO_ITEM CSL_CITATION {"citationID":"...", "citationItems":[...
            {"itemData":{"abstract":"...很长的英文摘要..."}}]}

    其 JSON 含**嵌套括号**，正则无法配对，因此用括号计数器逐字符扫描。

    返回 (处理后文本, 删除的块数)。
    """
    count = 0
    out: list[str] = []
    i = 0
    n = len(text)
    while True:
        j = text.find(anchor, i)
        if j < 0:
            out.append(text[i:])
            break
        out.append(text[i:j])
        # 跳过 anchor 与其后的空白，找到第一个 '{'
        k = j + len(anchor)
        while k < n and text[k] in " \t":
            k += 1
        if k >= n or text[k] != "{":
            # 没有 JSON 体，只删除 anchor 本身
            i = j + len(anchor)
            count += 1
            continue
        # 括号配对扫描（考虑字符串内的引号与转义）
        depth = 0
        in_str = False
        esc = False
        p = k
        while p < n:
            ch = text[p]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            else:
                if ch == '"':
                    in_str = True
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        p += 1
                        break
            p += 1
        i = p
        count += 1
    return "".join(out), count





def _cjk_count(t: str) -> int:
    return len(re.findall(r"[\u4e00-\u9fff]", t))


def clean(text: str) -> tuple[str, CleanReport]:
    """执行清洗，返回 (干净文本, 报告)。"""
    rep = CleanReport()
    rep.raw_chars = len(text)
    rep.raw_cjk = _cjk_count(text)
    rep.quality_before = rep.raw_cjk / max(rep.raw_chars, 1)

    # ---- ① 去引文元数据 ----
    n0 = len(text)
    # 1a. 括号配对删除 Zotero/Mendeley 引文 JSON 块（含嵌套）
    for anchor in ("ADDIN ZOTERO_ITEM CSL_CITATION",
                   "ADDIN ZOTERO_ITEM",
                   "ADDIN ZOTERO_BIBL",
                   "ADDIN CSL_BIBLIOGRAPHY",
                   "ADDIN EN.CITATION"):
        text, k = _strip_balanced_json(text, anchor)
        rep.citation_blocks += k
    # 1b. 正则清理残余标记
    for p in CITATION_PATTERNS:
        text = p.sub("", text)
    rep.removed_citation_chars = n0 - len(text)

    # ---- ② 去页眉页脚 ----
    n1 = len(text)
    for p in HEADER_PATTERNS:
        text = p.sub("", text)
    rep.removed_header_chars = n1 - len(text)

    # ---- ③ 去参考文献区 ----
    cut = len(text)
    for p in REFERENCE_MARKERS:
        m = p.search(text)
        if m and m.start() > len(text) * 0.5:   # 只在文档后半段截断
            cut = min(cut, m.start())
    if cut < len(text):
        rep.removed_reference_chars = len(text) - cut
        text = text[:cut]

    # ---- ④ 去不可见字符 ----
    before = len(text)
    text = INVISIBLE.sub("", text)
    rep.removed_invisible = before - len(text)

    # ---- ⑤ 规范化空白 ----
    text = re.sub(r"[ \t\u3000]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = "\n".join(l.rstrip() for l in text.split("\n"))
    text = text.strip()

    rep.clean_chars = len(text)
    rep.clean_cjk = _cjk_count(text)
    rep.quality_after = rep.clean_cjk / max(rep.clean_chars, 1)

    # ---- 质量判定 ----
    if rep.quality_after >= 0.55:
        rep.verdict = "GOOD（可直接用于知识抽取）"
    elif rep.quality_after >= 0.35:
        rep.verdict = "FAIR（可用，但建议人工抽查）"
    else:
        rep.verdict = "POOR（中文占比过低，需检查清洗规则）"
        rep.notes.append("清洗后中文占比仍偏低，可能存在未识别的噪声类型")

    if rep.quality_before < 0.35:
        rep.notes.append(
            f"原文中文占比仅 {rep.quality_before:.1%}，"
            f"主要噪声为引文元数据（{rep.citation_blocks} 个块）"
        )

    return text, rep


# ============================================================================
# CLI
# ============================================================================

def main() -> int:
    ap = argparse.ArgumentParser(description="领域语料清洗器")
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", default="")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--report-json", default="")
    args = ap.parse_args()

    if not os.path.exists(args.input):
        print(f"[ERROR] 文件不存在: {args.input}", file=sys.stderr)
        return 2

    with open(args.input, encoding="utf-8", errors="replace") as f:
        raw = f.read()

    text, rep = clean(raw)
    rep.src = os.path.basename(args.input)

    if args.report:
        print("=" * 68)
        print("  语料清洗报告")
        print("=" * 68)
        print(f"  文件              : {rep.src}")
        print(f"  原始字符数        : {rep.raw_chars:,}")
        print(f"  原始中文字符      : {rep.raw_cjk:,}  (占比 {rep.quality_before:.1%})")
        print("-" * 68)
        print(f"  去除引文元数据    : {rep.removed_citation_chars:,} 字符"
              f"  ({rep.citation_blocks} 个块)")
        print(f"  去除页眉页脚      : {rep.removed_header_chars:,} 字符")
        print(f"  去除参考文献区    : {rep.removed_reference_chars:,} 字符")
        print(f"  去除不可见字符    : {rep.removed_invisible:,} 字符")
        print("-" * 68)
        print(f"  清洗后字符数      : {rep.clean_chars:,}")
        print(f"  清洗后中文字符    : {rep.clean_cjk:,}  (占比 {rep.quality_after:.1%})")
        print(f"  ★ 中文占比提升    : {rep.quality_before:.1%} → {rep.quality_after:.1%}")
        print(f"  质量判定          : {rep.verdict}")
        for note in rep.notes:
            print(f"    · {note}")
        print("=" * 68)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"\n  干净语料已保存: {args.out}")

    if args.report_json:
        with open(args.report_json, "w", encoding="utf-8") as f:
            json.dump(asdict(rep), f, ensure_ascii=False, indent=2)
        print(f"  报告已保存: {args.report_json}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
