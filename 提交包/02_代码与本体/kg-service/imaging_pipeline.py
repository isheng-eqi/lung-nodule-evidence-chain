#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
图文类数据资产生成器 + VLM 识别流水线
================================================================

对应赛题要求：
  "实现对文本、表格、图文等多元行业数据的统一识别、理解与资产标识。"

本模块演示**图文类资产的完整处理链路**：

    ┌──────────────────────────────────────────────────────────┐
    │  第 1 步  生成/接收影像结构化报告图片（图文类数据资产）      │
    │  第 2 步  VLM 识别：从图片中抽取结构化患者事实              │
    │  第 3 步  推理：把抽取的事实送入知识图谱推理引擎            │
    │  第 4 步  输出：带条款级溯源的处置建议                      │
    └──────────────────────────────────────────────────────────┘

这与"文本类资产"的处理路径形成对照：
    文本类：文档 → 条款切分 → 本体对齐 → 图谱
    图文类：图片 → VLM 识别 → 事实抽取 → 图谱推理

用法：
    # 生成样例报告图片
    python3 imaging_pipeline.py --generate --out report_sample.png

    # 对图片做 VLM 识别 + 推理
    python3 imaging_pipeline.py --image report_sample.png --run

    # 全流程（生成 → 识别 → 推理）
    python3 imaging_pipeline.py --full --out report_sample.png
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import urllib.request

# ============================================================================
# 一、图文类数据资产生成
# ============================================================================

REPORT_CONTENT = {
    "title": "肺结节影像结构化报告",
    "hospital": "××县人民医院  放射科",
    "exam": "胸部低剂量CT（LDCT）",
    "notice": "本报告为按标准格式构造的样例，不含真实患者信息",
    "sections": [
        ("结节描述", [
            ("位置", "右肺上叶尖段"),
            ("最大径", "8 mm"),
            ("密度类型", "混杂性磨玻璃结节（mGGN）"),
            ("实性成分", "2 mm"),
            ("边缘", "可见毛刺征"),
            ("分叶", "无"),
            ("胸膜凹陷", "无"),
            ("血管集束", "无"),
            ("钙化", "无"),
            ("既往对比", "与 2026-04-10 前片比较，大小无明显变化"),
        ]),
        ("患者信息（脱敏）", [
            ("年龄", "55"),
            ("性别", "男"),
            ("吸烟史", "30 年，吸烟指数 600 年支"),
            ("职业暴露", "无"),
            ("慢性肺病", "无"),
            ("肿瘤史或家族史", "无"),
        ]),
    ],
    "impression": [
        "右肺上叶尖段混杂性磨玻璃结节，最大径 8mm，实性成分 2mm，伴毛刺征。",
        "结合患者长期吸烟史，属肺癌高危人群。",
    ],
    "recommendation": "建议结合临床共识进行规范随访管理。",
}


def generate_report_image(out_path: str) -> str:
    """生成一张影像结构化报告图片（模拟报告单形态）。"""
    from PIL import Image, ImageDraw, ImageFont

    W, H = 1000, 1180
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)

    # 查找中文字体
    font_candidates = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc",
    ]
    fpath = next((p for p in font_candidates if os.path.exists(p)), None)
    if not fpath:
        # 回退：用默认字体（中文可能显示为方块，但流程仍可验证）
        f_big = f_mid = f_small = ImageFont.load_default()
    else:
        f_big = ImageFont.truetype(fpath, 30)
        f_mid = ImageFont.truetype(fpath, 22)
        f_small = ImageFont.truetype(fpath, 19)

    y = 40
    # 标题
    d.text((W // 2, y), REPORT_CONTENT["title"], font=f_big, fill="black", anchor="mm")
    y += 46
    d.text((W // 2, y), REPORT_CONTENT["hospital"], font=f_small, fill="#444444", anchor="mm")
    y += 34
    d.line([(50, y), (W - 50, y)], fill="#999999", width=2)
    y += 22

    # 检查项目
    d.text((60, y), f"检查项目：{REPORT_CONTENT['exam']}", font=f_small, fill="black")
    y += 30
    d.text((60, y), f"报告类型：影像结构化报告文本", font=f_small, fill="black")
    y += 30
    d.text((60, y), REPORT_CONTENT["notice"], font=f_small, fill="#aa0000")
    y += 36
    d.line([(50, y), (W - 50, y)], fill="#cccccc", width=1)
    y += 20

    # 各分节
    for sec_title, rows in REPORT_CONTENT["sections"]:
        d.text((60, y), f"【{sec_title}】", font=f_mid, fill="#003366")
        y += 36
        for k, v in rows:
            d.text((80, y), k, font=f_small, fill="#333333")
            d.text((230, y), "：", font=f_small, fill="#333333")
            d.text((250, y), v, font=f_small, fill="black")
            y += 30
        y += 12

    # 影像学印象
    d.text((60, y), "【影像学印象】", font=f_mid, fill="#003366")
    y += 36
    for line in REPORT_CONTENT["impression"]:
        d.text((80, y), "· " + line, font=f_small, fill="black")
        y += 30
    y += 12

    # 报告医师建议
    d.text((60, y), "【报告医师建议】", font=f_mid, fill="#003366")
    y += 36
    d.text((80, y), REPORT_CONTENT["recommendation"], font=f_small, fill="black")
    y += 50

    d.line([(50, y), (W - 50, y)], fill="#999999", width=1)
    y += 20
    d.text((60, y), "报告医师：___（样例）        审核医师：___（样例）", font=f_small, fill="#666666")
    y += 30
    d.text((60, y), "报告日期：2026-10-10", font=f_small, fill="#666666")

    img.save(out_path, "PNG")
    return out_path


# ============================================================================
# 二、VLM 识别
# ============================================================================

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


def vlm_extract(image_path: str, api_key: str,
                model: str = "Qwen/Qwen3-VL-8B-Instruct",
                base_url: str = "https://api.siliconflow.cn/v1/chat/completions"
                ) -> dict:
    """调用 VLM 从报告图片中抽取结构化事实。"""
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()

    payload = {
        "model": model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image_url",
                 "image_url": {"url": f"data:image/png;base64,{b64}"}},
                {"type": "text", "text": VLM_EXTRACT_PROMPT},
            ],
        }],
        "max_tokens": 800,
        "temperature": 0.1,
    }
    req = urllib.request.Request(
        base_url, data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {api_key}",
                 "Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        resp = json.loads(r.read().decode())

    text = resp["choices"][0]["message"]["content"]
    # 从回复中提取 JSON
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return {"_raw": text, "_error": "未找到 JSON"}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError as e:
        return {"_raw": text, "_error": f"JSON 解析失败: {e}"}


# ============================================================================
# 三、事实 → 推理引擎输入
# ============================================================================

def facts_to_description(facts: dict) -> str:
    """把 VLM 抽取的结构化事实转成推理引擎的自然语言输入。"""
    parts = []
    if facts.get("年龄"):
        parts.append(f"{facts['年龄']}岁")
    if facts.get("性别"):
        parts.append(facts["性别"] + "性")
    if facts.get("最大径_mm") is not None:
        parts.append(f"{facts['最大径_mm']}mm")
    if facts.get("密度类型"):
        parts.append(facts["密度类型"])
    if facts.get("实性成分_mm") is not None:
        parts.append(f"实性成分{facts['实性成分_mm']}mm")
    if facts.get("吸烟年数"):
        parts.append(f"吸烟{facts['吸烟年数']}年")
    for feat in facts.get("影像特征") or []:
        parts.append(feat)
    return "，".join(parts) + "，该如何处理？"


def run_reasoning(description: str) -> dict:
    """调用本地推理引擎（复用 MCP Server 模块）。"""
    sys.path.insert(0, "/tmp")
    try:
        import kg_mcp_server as kg
    except ImportError:
        return {"_error": "无法导入推理引擎（需在 nexent-mcp 容器内运行）"}
    return kg.run_inference(description)


# ============================================================================
# CLI
# ============================================================================

def main() -> int:
    ap = argparse.ArgumentParser(description="图文类数据资产处理流水线")
    ap.add_argument("--generate", action="store_true", help="生成样例报告图片")
    ap.add_argument("--image", default="", help="待识别的报告图片")
    ap.add_argument("--run", action="store_true", help="执行 VLM 识别 + 推理")
    ap.add_argument("--full", action="store_true", help="全流程：生成→识别→推理")
    ap.add_argument("--out", default="/tmp/report_sample.png")
    ap.add_argument("--api-key", default=os.environ.get("SILICONFLOW_KEY", ""))
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    result: dict = {}

    # ---- 第 1 步：生成 ----
    if args.generate or args.full:
        path = generate_report_image(args.out)
        sz = os.path.getsize(path)
        print("=" * 70)
        print("  第 1 步  生成图文类数据资产")
        print("=" * 70)
        print(f"  输出: {path}  ({sz / 1024:.1f} KB)")
        result["image"] = path
        result["image_size"] = sz
        if not (args.run or args.full):
            return 0

    img = args.image or args.out
    if not os.path.exists(img):
        print(f"[ERROR] 图片不存在: {img}", file=sys.stderr)
        return 2

    # ---- 第 2 步：VLM 识别 ----
    if args.run or args.full:
        print()
        print("=" * 70)
        print("  第 2 步  VLM 识别（图文类资产 → 结构化事实）")
        print("=" * 70)
        if not args.api_key:
            print("  [ERROR] 需要 --api-key 或环境变量 SILICONFLOW_KEY", file=sys.stderr)
            return 2
        facts = vlm_extract(img, args.api_key)
        result["vlm_facts"] = facts
        print(json.dumps(facts, ensure_ascii=False, indent=2))

        if facts.get("_error"):
            print(f"\n  ⚠️ 识别异常: {facts['_error']}")
            return 1

        # ---- 第 3 步：推理 ----
        print()
        print("=" * 70)
        print("  第 3 步  送入知识图谱推理引擎")
        print("=" * 70)
        desc = facts_to_description(facts)
        print(f"  转换后的描述: {desc}")
        inf = run_reasoning(desc)
        result["inference"] = inf

        if inf.get("_error"):
            print(f"  ⚠️ 推理异常: {inf['_error']}")
            return 1

        print()
        print(f"  覆盖率  : {inf.get('coverage')}")
        print(f"  可溯源  : {inf.get('traceable')}")
        print(f"  结论    : {inf.get('conclusion', '')[:150]}")
        print(f"  条款    : {inf.get('clause')} {inf.get('clause_title', '')}")
        print(f"  随访    : {inf.get('follow_up', '')}")
        if inf.get("referral"):
            print(f"  分级诊疗: {inf['referral']}")
        for cd in inf.get("contraindications", []):
            print(f"  禁忌    : {cd.get('reason', '')}")
        print(f"\n  推理链（{len(inf.get('chain', []))} 跳）:")
        for st in inf.get("chain", []):
            cl = f" [{st['clause']}]" if st.get("clause") else ""
            print(f"    跳{st['hop']} {st['rule']}{cl}")
            print(f"        {st['from']}  →  {st['to']}")

        # ---- 第 4 步：资产标识 ----
        print()
        print("=" * 70)
        print("  第 4 步  生成资产标识")
        print("=" * 70)
        import hashlib
        h = hashlib.sha256(open(img, "rb").read()).hexdigest()[:16]
        asset = {
            "asset_id": f"AST-{h[:8].upper()}",
            "asset_name": os.path.basename(img),
            "modality": "image",
            "file_format": "png",
            "size_bytes": os.path.getsize(img),
            "content_hash": h,
            "structure_type": "影像结构化报告（图像形态）",
            "authority_level": "L4",
            "compliance": "PUBLIC",
            "contains_patient_data": False,
            "concepts": [facts.get("密度类型")] if facts.get("密度类型") else [],
            "clauses": [inf.get("clause")] if inf.get("clause") else [],
            "processed_by": "imaging_pipeline + VLM",
            "status": "ALIGNED",
        }
        result["asset"] = asset
        print(json.dumps(asset, ensure_ascii=False, indent=2))

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"\n  结果已保存: {args.json}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
