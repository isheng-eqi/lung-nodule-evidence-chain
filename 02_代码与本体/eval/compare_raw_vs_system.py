#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
对照实验：裸大模型 vs 本系统
================================================================

目的
----
证明本项目的**不可替代性** —— 不是我们声称自己好，而是让数据说话。

对照设计
--------
同一批临床问题，分别交给：

  A. **裸大模型**（DeepSeek-V3，无知识库、无图谱、无工具）
     提示词只给角色，不给指南内容，模拟"医生直接问大模型"

  B. **本系统**（Nexent 智能体 + 自研知识图谱 MCP + 知识库检索）
     走完整的检索-推理双驱动流程

对比维度（均可机器或人工核验）
------------------------------
  1. **条款级溯源** —— 是否给出【推荐意见N】
  2. **随访间隔一致性** —— 与《2024 共识》原文是否一致
  3. **指南来源标注** —— 引用的是中国共识还是国外指南
  4. **禁忌提示** —— 是否提示 PET-CT 的适用边界
  5. **免责声明** —— 是否声明不替代医生判断

用法
----
    python3 compare_raw_vs_system.py --out comparison.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.request

SILICONFLOW_URL = "https://api.siliconflow.cn/v1/chat/completions"
RAW_MODEL = "deepseek-ai/DeepSeek-V3"

# 与端到端验证相同的测试场景（便于横向对照）
CASES = [
    {
        "id": "C1",
        "topic": "典型正例 mGGN ≤8mm",
        "question": "一位55岁男性，8mm混合磨玻璃结节，实性成分2mm，吸烟30年，该怎么随访？",
        "expected_clause": "推荐意见14",
        "expected_followup": "3、6、12 和 24 个月",
        "expected_contra": "PET-CT 不推荐",
    },
    {
        "id": "C2",
        "topic": "mGGN >8mm",
        "question": "男，62岁，15mm混杂性磨玻璃结节，吸烟40年，有毛刺征，该如何处理？",
        "expected_clause": "推荐意见15",
        "expected_followup": "3 个月",
        "expected_contra": "PET-CT",
    },
    {
        "id": "C3",
        "topic": "纯磨玻璃结节 6mm",
        "question": "女，48岁，右肺上叶6mm纯磨玻璃结节，无吸烟史，该如何处理？",
        "expected_clause": "推荐意见13",
        "expected_followup": "6 个月",
        "expected_contra": "",
    },
    {
        "id": "C4",
        "topic": "实性结节 ≤8mm 无危险因素",
        "question": "患者45岁，7mm实性结节，无吸烟史，无其他危险因素，怎么随访？",
        "expected_clause": "推荐意见10",
        "expected_followup": "12 个月",
        "expected_contra": "",
    },
    {
        "id": "C5",
        "topic": "禁忌场景",
        "question": "一位55岁男性，8mm混合磨玻璃结节，实性成分2mm，能否做PET-CT评估？",
        "expected_clause": "推荐意见15",
        "expected_followup": "",
        "expected_contra": "不推荐",
    },
    {
        "id": "C6",
        "topic": "信息不足（应追问）",
        "question": "我有肺结节，该怎么办？",
        "expected_clause": "",
        "expected_followup": "",
        "expected_contra": "",
    },
]

# 裸模型提示词：只给角色，**不给任何指南内容**，模拟医生直接问大模型
RAW_SYSTEM = "你是一名呼吸科医生，请根据你的医学知识回答患者的问题。"


def call_raw(question: str, api_key: str, retry: int = 2) -> dict:
    """调用裸大模型（无知识库、无工具）。"""
    payload = {
        "model": RAW_MODEL,
        "messages": [
            {"role": "system", "content": RAW_SYSTEM},
            {"role": "user", "content": question},
        ],
        "max_tokens": 1200,
        "temperature": 0.2,
    }
    for attempt in range(retry + 1):
        try:
            req = urllib.request.Request(
                SILICONFLOW_URL,
                data=json.dumps(payload).encode(),
                headers={"Authorization": f"Bearer {api_key}",
                         "Content-Type": "application/json"},
                method="POST")
            with urllib.request.urlopen(req, timeout=180) as r:
                d = json.loads(r.read().decode())
            return {"ok": True, "text": d["choices"][0]["message"]["content"],
                    "model": d.get("model"), "usage": d.get("usage")}
        except Exception as e:
            if attempt == retry:
                return {"ok": False, "error": f"{type(e).__name__}: {e}"}
            time.sleep(3)
    return {"ok": False, "error": "unreachable"}


def analyze(text: str, case: dict) -> dict:
    """对一段回答做可机器核验的指标提取。"""
    t = text or ""
    # 条款级溯源：是否出现【推荐意见N】
    cite = re.findall(r"【推荐意见\s*(\d+)\s*】", t)
    # 中文指南出处
    cn_guide = bool(re.search(r"中国肺癌|肺结节诊治中国专家共识|中华医学会|中国专家共识", t))
    # 国外指南出处
    foreign = re.findall(r"(Fleischner|NCCN|ACCP|BTS|Lung-?RADS|ACR)", t)
    # 随访间隔：抓"数字、数字"形式
    intervals = re.findall(r"(\d+\s*[、,，和\-~]\s*\d+(?:\s*[、,，和\-~]\s*\d+)*)\s*个?月", t)
    # PET-CT 相关
    has_pet = bool(re.search(r"PET", t, re.I))
    pet_not_rec = bool(re.search(r"PET[^。\n]{0,40}(不推荐|不建议|不适用|假阴性)", t, re.I))
    # 免责声明
    disclaimer = bool(re.search(r"仅供.{0,6}参考|不替代|不构成诊断|请.{0,4}医生", t))
    # 是否追问
    ask_back = bool(re.search(r"请问|需要.{0,4}(提供|补充)|请.{0,4}(提供|补充)|多少毫米|直径是多少|最大径", t))

    # 期望项命中
    hit_clause = bool(case["expected_clause"]) and (
        case["expected_clause"].replace("推荐意见", "") in cite)
    hit_fu = False
    if case["expected_followup"]:
        norm = re.sub(r"\s", "", case["expected_followup"])
        hit_fu = any(re.sub(r"\s", "", i) in norm or norm in re.sub(r"\s", "", i)
                     for i in intervals) or (norm[:4] in re.sub(r"\s", "", t))
    hit_contra = False
    if case["expected_contra"]:
        hit_contra = pet_not_rec or (has_pet and bool(re.search(r"不推荐|不建议|不适用", t)))

    return {
        "length": len(t),
        "clauses_cited": cite,
        "clauses_cited_count": len(cite),
        "has_clause_citation": len(cite) > 0,
        "cites_cn_guideline": cn_guide,
        "cites_foreign_guideline": sorted(set(foreign)),
        "followup_intervals": intervals,
        "mentions_pet": has_pet,
        "pet_appropriately_cautioned": pet_not_rec,
        "has_disclaimer": disclaimer,
        "asks_back": ask_back,
        "hit_expected_clause": hit_clause,
        "hit_expected_followup": hit_fu,
        "hit_expected_contra": hit_contra if case["expected_contra"] else None,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="裸模型 vs 本系统 对照实验")
    ap.add_argument("--out", required=True)
    ap.add_argument("--raw-only", action="store_true",
                    help="只跑裸模型（本系统的数据从已有记录读取）")
    args = ap.parse_args()

    api_key = os.environ.get("SILICONFLOW_KEY", "")
    if not api_key:
        print("[ERROR] 需要环境变量 SILICONFLOW_KEY", file=sys.stderr)
        return 2

    result = {"model": RAW_MODEL, "cases": []}

    print("=" * 76)
    print("  对照实验：裸大模型（无知识库/无图谱/无工具）")
    print("=" * 76)
    for c in CASES:
        print(f"\n[{c['id']}] {c['topic']}")
        print(f"  Q: {c['question']}")
        r = call_raw(c["question"], api_key)
        if not r.get("ok"):
            print(f"  ❌ 调用失败: {r.get('error')}")
            result["cases"].append({**c, "raw": {"ok": False, "error": r.get("error")}})
            continue
        a = analyze(r["text"], c)
        print(f"  回答长度      : {a['length']} 字符")
        print(f"  条款级溯源    : {'有' if a['has_clause_citation'] else '❌ 无'}"
              f"{' ' + str(a['clauses_cited']) if a['clauses_cited'] else ''}")
        print(f"  引用中国指南  : {'是' if a['cites_cn_guideline'] else '❌ 否'}")
        print(f"  引用国外指南  : {a['cites_foreign_guideline'] or '（无）'}")
        print(f"  随访间隔      : {a['followup_intervals'] or '（未提取到）'}")
        print(f"  命中期望条款  : {'✅' if a['hit_expected_clause'] else '❌'}")
        if c["expected_followup"]:
            print(f"  命中期望间隔  : {'✅' if a['hit_expected_followup'] else '❌'}"
                  f"  (期望 {c['expected_followup']})")
        print(f"  免责声明      : {'有' if a['has_disclaimer'] else '❌ 无'}")
        print(f"  是否追问      : {'是' if a['asks_back'] else '否'}")
        result["cases"].append({**c, "raw": {"ok": True, "text": r["text"],
                                             "analysis": a, "usage": r.get("usage")}})
        time.sleep(2)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # 汇总
    ok = [c for c in result["cases"] if c["raw"].get("ok")]
    n = len(ok)
    print()
    print("=" * 76)
    print(f"  裸模型汇总（{n} 个场景）")
    print("=" * 76)
    if n:
        cite = sum(1 for c in ok if c["raw"]["analysis"]["has_clause_citation"])
        cn = sum(1 for c in ok if c["raw"]["analysis"]["cites_cn_guideline"])
        fc = sum(1 for c in ok if c["raw"]["analysis"]["cites_foreign_guideline"])
        dis = sum(1 for c in ok if c["raw"]["analysis"]["has_disclaimer"])
        cl = sum(1 for c in ok if c["raw"]["analysis"]["hit_expected_clause"])
        print(f"  给出条款级溯源    : {cite}/{n}")
        print(f"  引用中国指南      : {cn}/{n}")
        print(f"  引用国外指南      : {fc}/{n}")
        print(f"  给出免责声明      : {dis}/{n}")
        print(f"  命中期望条款      : {cl}/{n}")
    print(f"\n  已保存: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
