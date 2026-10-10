#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MedRepBench 真实脱敏数据集上的多模态识别评测
================================================================

要解决的问题
------------
独立审计指出：
  「**图文证据规模**：1 张**自造**样例图，VLM 跑 1 次，报'8/8 字段（准确率 100%）'。」
  「**放过了手边唯一可用的外部数据** —— MedRepBench 的 1,087 条检查报告
    足以**独立评测多模态识别链路**。」

本脚本用 MedRepBench（HuggingFace，CC-BY-NC-4.0）的**真实脱敏中文医疗报告图片**
评测本项目的多模态抽取能力。

★ 重要的任务界定（必须先说清）
------------------------------
MedRepBench 的客观抽取任务是「**实验室检验项表格抽取**」，
而本项目的核心任务是「**肺结节影像报告 → 处置决策**」。

**两者任务不同。** 因此本评测**能证明什么、不能证明什么**：

| 能证明 | 不能证明 |
|---|---|
| 多模态链路的**识别层**在**真实脱敏报告**上的字段抽取能力 | **不能**证明结节处置决策的正确性 |
| VLM 抽取在**不同版式/不同医院**报告上的鲁棒性 | **不能**替代结节场景的临床验证 |
| 「多模态异构数据统一识别与资产标识」这一赛题要求的落地程度 | —— |

**即：这是"识别层"的独立评测，不是"决策层"的评测。**

判定口径
--------
按 MedRepBench 官方 `scripts/evaluate_objective.py` 的口径复刻：
  · 按 `item_name` 归一化后匹配（预测项 ↔ 参考项，一一配对）
  · 匹配上的项，逐个字段比对
  · 指标 = **field-level recall**（字段级召回）

用法
----
    python3 medrep_bench_eval.py \
        --meta datasets-meta-zhCN.csv \
        --img-dir censored/ \
        --n 30 --out medrep_eval.json
"""

from __future__ import annotations

import argparse
import base64
import csv
import json
import os
import random
import re
import sys
import time
import urllib.request

VLM_MODEL = "Qwen/Qwen3-VL-8B-Instruct"
VLM_URL = "https://api.siliconflow.cn/v1/chat/completions"

# 官方 objective_extraction_prompt 的中文改写版（保留字段定义与 JSON 结构要求）
VLM_PROMPT = """你是一个医疗检验报告的结构化信息抽取器。
请仔细阅读这张检验报告图片，抽取其中**全部**检验项目，并以 JSON 数组输出。

每个元素必须包含以下字段：
- `item_name`: 检验项目名称
- `item_value`: 观测值
- `item_unit`: 单位（无则填空字符串）
- `item_range`: 参考范围（无则填空字符串）
- `is_abnormal`: 异常则为 "1"，正常为 "0"，无法判断填空字符串

只输出 JSON 数组，不要任何解释文字、不要 Markdown 代码块。
示例：
[{"item_name": "PT", "item_value": "12.80", "item_unit": "s", "item_range": "9-14", "is_abnormal": "0"}]"""

FIELDS = ["item_name", "item_value", "item_unit", "item_range", "is_abnormal"]


# ============================================================================
# 官方口径的归一化与匹配
# ============================================================================

def normalize_text(value) -> str:
    if value is None:
        return ""
    s = str(value).strip().lower()
    s = re.sub(r"\s+", "", s)            # 去所有空白（官方口径）
    s = s.replace("（", "(").replace("）", ")")
    return s


def normalize_number_like(value) -> str:
    s = normalize_text(value)
    s = s.replace(",", "")
    # 去掉无意义的尾随 0（12.80 == 12.8）
    m = re.fullmatch(r"([+-]?\d+(?:\.\d+)?)", s)
    if m:
        try:
            f = float(m.group(1))
            return f"{f:g}"
        except ValueError:
            return s
    return s


def field_equal(field: str, pred, ref) -> bool:
    if field in ("item_value", "item_range"):
        return normalize_number_like(pred) == normalize_number_like(ref)
    return normalize_text(pred) == normalize_text(ref)


def match_items(pred_items: list, ref_items: list) -> list:
    """按 item_name 一一配对（官方口径）。"""
    matches = []
    used: set[int] = set()
    for ref in ref_items:
        ref_name = normalize_text(ref.get("item_name"))
        for i, pred in enumerate(pred_items):
            if i in used:
                continue
            if normalize_text(pred.get("item_name")) == ref_name:
                used.add(i)
                matches.append((pred, ref))
                break
    return matches


# ============================================================================

def vlm_extract(image_path: str, api_key: str) -> list:
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    ext = os.path.splitext(image_path)[1].lstrip(".").lower()
    mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg",
            "png": "image/png", "webp": "image/webp"}.get(ext, "image/png")
    payload = {
        "model": VLM_MODEL,
        "messages": [{"role": "user", "content": [
            {"type": "image_url",
             "image_url": {"url": f"data:{mime};base64,{b64}"}},
            {"type": "text", "text": VLM_PROMPT}]}],
        "max_tokens": 3000, "temperature": 0.1,
    }
    req = urllib.request.Request(
        VLM_URL, data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {api_key}",
                 "Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=180) as r:
        resp = json.loads(r.read().decode())
    text = resp["choices"][0]["message"]["content"]
    m = re.search(r"\[[\s\S]*\]", text)
    if not m:
        return []
    try:
        arr = json.loads(m.group(0))
        return arr if isinstance(arr, list) else []
    except json.JSONDecodeError:
        return []


def main() -> int:
    ap = argparse.ArgumentParser(description="MedRepBench 多模态识别评测")
    ap.add_argument("--meta", required=True)
    ap.add_argument("--img-dir", required=True)
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--seed", type=int, default=20261010)
    ap.add_argument("--out", default="medrep_eval.json")
    args = ap.parse_args()

    api_key = os.environ.get("SILICONFLOW_KEY", "")
    if not api_key:
        print("[ERROR] 需要 SILICONFLOW_KEY", file=sys.stderr)
        return 2

    # ---- 选样：只取有 items 标注、且项数 >= 3 的报告 ----
    rows = list(csv.DictReader(open(args.meta, encoding="utf-8")))
    cands = []
    for r in rows:
        try:
            items = json.loads(r.get("items") or "[]")
        except json.JSONDecodeError:
            continue
        if not isinstance(items, list) or len(items) < 3:
            continue
        p = os.path.join(args.img_dir, r["image"])
        if os.path.exists(p):
            cands.append((r["image"], items, json.loads(r.get("meta") or "{}"), p))
    random.Random(args.seed).shuffle(cands)
    sample = cands[:args.n]

    print("=" * 84)
    print("  MedRepBench 真实脱敏数据集 · 多模态识别评测")
    print("=" * 84)
    print(f"  有标注候选: {len(cands)} 份   本次抽样: {len(sample)} 份")
    print(f"  判定口径  : 按 item_name 匹配 + field-level recall（官方 evaluate_objective.py）")
    print()
    print(f"  {'#':<4}{'图片':<40}{'参考项':<7}{'预测项':<7}{'匹配':<6}{'字段级召回'}")
    print("  " + "-" * 78)

    correct = {f: 0 for f in FIELDS}
    totals = {f: 0 for f in FIELDS}
    results = []

    for i, (img_name, ref_items, meta, img_path) in enumerate(sample, 1):
        try:
            pred_items = vlm_extract(img_path, api_key)
        except Exception as e:                              # noqa: BLE001
            print(f"  {i:<4}{img_name[:38]:<40}调用失败 {type(e).__name__}")
            results.append({"image": img_name, "ok": False,
                            "error": f"{type(e).__name__}: {e}"})
            continue

        matches = match_items(pred_items, ref_items)
        rep_correct = 0
        rep_total = 0
        for pred, ref in matches:
            for f in FIELDS:
                totals[f] += 1
                if field_equal(f, pred.get(f), ref.get(f)):
                    correct[f] += 1
                    rep_correct += 1
                rep_total += 1
        # 未匹配上的参考项，其 5 个字段全部计入分母（漏检）
        unmatched = len(ref_items) - len(matches)
        for _ in range(unmatched):
            for f in FIELDS:
                totals[f] += 1

        rate = (rep_correct / rep_total) if rep_total else 0.0
        print(f"  {i:<4}{img_name[:38]:<40}{len(ref_items):<7}{len(pred_items):<7}"
              f"{len(matches):<6}{rate*100:.1f}%")
        results.append({
            "image": img_name, "ok": True, "meta": meta,
            "ref_count": len(ref_items), "pred_count": len(pred_items),
            "matched": len(matches), "field_correct": rep_correct,
            "field_total": rep_total,
        })
        time.sleep(1)

    print()
    print("=" * 84)
    print("  ★ 字段级召回（官方口径）")
    print("=" * 84)
    for f in FIELDS:
        t = totals[f]
        c = correct[f]
        r = c / t if t else 0.0
        print(f"  {f:<16}{c:>5}/{t:<6}{r*100:>8.1f}%  {'█' * int(r * 24)}")
    avg = sum(correct[f] / totals[f] for f in FIELDS if totals[f]) / len(FIELDS)
    print("  " + "-" * 62)
    print(f"  {'平均':<16}{'':>5}{'':<6}{avg*100:>8.1f}%")
    print("=" * 84)

    report = {
        "dataset": "MedRepBench (HuggingFace: MedRepBench/MedRepBench)",
        "license": "CC-BY-NC-4.0",
        "task": "objective_extraction —— 实验室检验项表格抽取",
        "metric": "field-level recall（官方 evaluate_objective.py 口径）",
        "sample_size": len(sample),
        "seed": args.seed,
        "vlm_model": VLM_MODEL,
        "field_recall": {f: {"correct": correct[f], "total": totals[f],
                             "recall": round(correct[f] / totals[f], 4) if totals[f] else 0.0}
                         for f in FIELDS},
        "average_recall": round(avg, 4),
        "results": results,
        "scope_note": (
            "★ 任务界定：MedRepBench 的客观抽取任务是「实验室检验项表格抽取」，"
            "与本项目核心的「肺结节影像报告 → 处置决策」任务不同。"
            "本评测证明的是**多模态链路识别层在真实脱敏报告上的字段抽取能力**，"
            "**不能**证明结节处置决策的正确性，也不替代结节场景的临床验证。"),
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"  报告已保存: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
