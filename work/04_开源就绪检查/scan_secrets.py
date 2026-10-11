#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""凭据泄漏扫描（可复现、可自证）

★ 为什么需要这个脚本
====================
任务 4 的第一版扫描报了"无命中"。**结论是对的**（仓库确实没有真实凭据），
但**过程不足以支撑这个结论**：

  1. 没写清用的是什么扫描模式 → 别人无法复现
  2. 没报命中条数 → "没找到"和"确认没有"被混为一谈
  3. 没有逐条判定 → 有些命中是**正确做法**（如 os.environ.get），
     不判定就分不清"安全"和"泄漏"

**扫描报告必须能自证。** 本脚本按这个标准输出。

用法
----
    python3 scan_secrets.py --root . --out 扫描报告.md
"""
from __future__ import annotations

import argparse
import os
import re
import sys

# ---- 高危模式：真实凭据的形态 ----
HIGH = [
    (r"sk-[A-Za-z0-9]{20,}", "模型 API Key（sk- 开头）"),
    (r"nexent-[a-f0-9]{16,}", "Nexent 平台 Key"),
    (r"ghp_[A-Za-z0-9]{30,}", "GitHub Personal Access Token"),
    (r"AKIA[0-9A-Z]{16}", "AWS Access Key ID"),
    (r"Bearer [A-Za-z0-9._\-]{20,}", "硬编码的 Bearer 令牌"),
    (r"Nexent@[0-9]{4}", "平台账号口令"),
]

# ---- 中危模式：需要人工判定的形态 ----
MID = [
    (r"password\s*[:=]\s*[\"'][^\"']{4,}[\"']", "硬编码密码"),
    (r"passwd\s*[:=]\s*[\"'][^\"']{4,}[\"']", "硬编码密码"),
    (r"api[_-]?key\s*[:=]\s*[\"'][^\"']{8,}[\"']", "硬编码 API Key"),
    (r"secret[_-]?key\s*[:=]\s*[\"'][^\"']{8,}[\"']", "硬编码 Secret"),
    (r"os\.environ\.get\(\s*[\"'][^\"']+[\"']\s*,\s*[\"'][^\"']+[\"']\s*\)",
     "环境变量默认值（★ 通常安全，需看默认值是否敏感）"),
    (r"open\([^)]*key[^)]*\)\.read\(\)", "从文件读密钥（★ 正确做法）"),
    # ★ 这两个模式是复核时补的：命令行参数形态的外泄面
    (r"add_argument\(\s*[\"']--(api[-_]?key|token|password|secret)[\"']",
     "命令行参数接收密钥（★ 需看 default 是否硬编码）"),
    (r"[\"'][A-Z_]*(KEY|TOKEN|PASSWORD|SECRET|PASS)[A-Z_]*[\"']",
     "敏感环境变量名被引用（★ 通常安全，需确认未赋值）"),
]

# ---- 判定规则：命中这些特征的，判为「安全」 ----
SAFE_MARKERS = [
    (r"os\.environ\.get\([^)]*,\s*[\"']\s*[\"']\s*\)", "环境变量默认空串 —— 未硬编码"),
    (r"os\.environ\.get\(", "从环境变量读取 —— 正确做法"),
    (r"open\([^)]*\)\.read\(\)", "从文件读取 —— 代码中无值"),
    (r"<your_key>|<KEY>|<token>|YOUR_|xxxx", "占位符，非真实值"),
    (r"[<＜]\s*[A-Za-z_\u4e00-\u9fff]+\s*[>＞]", "占位符/格式说明"),
    (r"格式\s*`?Bearer\s+nexent-<hex>", "文档描述鉴权格式，不含真实值"),
]


def classify(path: str, line: str) -> tuple[str, str]:
    """返回 (判定, 理由)"""
    for pat, why in SAFE_MARKERS:
        if re.search(pat, line):
            return "安全", why
    # 本地默认口令：值本身就是"公开的本地默认值"
    if re.search(r"[\"']nexent@\d{4}[\"']", line) and "environ.get" in line:
        return "安全", "本地容器默认口令，非外部凭据"
    if re.search(r"[\"']nexent@\d{4}[\"']", line):
        return "需确认", "疑似本地默认口令，请确认是否对外可用"
    return "待判定", "需人工判断"


def scan(root: str):
    exts = (".md", ".json", ".py", ".txt", ".csv", ".yml", ".yaml", ".sh", ".toml", ".ini")
    skip_dirs = {".git", "__pycache__", "node_modules", ".venv", "venv"}
    hits = []
    for dp, dn, fs in os.walk(root):
        dn[:] = [d for d in dn if d not in skip_dirs]
        for f in fs:
            if not f.endswith(exts):
                continue
            p = os.path.join(dp, f)
            try:
                lines = open(p, encoding="utf-8", errors="ignore").read().split("\n")
            except Exception:
                continue
            for i, line in enumerate(lines, 1):
                matched = None
                for pat, label in HIGH:
                    if re.search(pat, line):
                        matched = ("高危", label)
                        break
                if not matched:
                    for pat, label in MID:
                        if re.search(pat, line):
                            matched = ("中危", label)
                            break
                if matched:
                    verdict, reason = classify(p, line)
                    # (文件, 行, 级别, 形态, 原文, 判定, 理由)
                    hits.append((os.path.relpath(p, root), i, matched[0],
                                 matched[1], line.strip(), verdict, reason))
    return hits


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    hits = scan(args.root)
    # 元组: (文件, 行, 级别, 形态, 原文, 判定, 理由)
    safe = [h for h in hits if h[5] == "安全"]
    need = [h for h in hits if h[5] != "安全"]

    L = []
    L.append("# 凭据泄漏扫描报告\n")
    L.append(f"- 扫描根目录：`{args.root}`")
    L.append(f"- 扫描文件类型：`.md .json .py .txt .csv .yml .yaml .sh .toml .ini`")
    L.append(f"- 高风险模式：**{len(HIGH)}** 条　中风险模式：**{len(MID)}** 条")
    L.append(f"- **命中总数：{len(hits)}**（判为安全 {len(safe)} / 需人工确认 {len(need)}）\n")

    L.append("## 扫描模式（可复现）\n")
    L.append("```")
    for pat, label in HIGH:
        L.append(f"[高危] {pat}    # {label}")
    for pat, label in MID:
        L.append(f"[中危] {pat}    # {label}")
    L.append("```\n")

    L.append("## 逐条命中与判定\n")
    if not hits:
        L.append("**无任何命中。**\n")
    else:
        L.append("| # | 文件:行 | 级别 | 形态 | 判定 | 理由 |")
        L.append("|---|---|---|---|---|---|")
        for n, h in enumerate(hits, 1):
            L.append(f"| {n} | `{h[0]}:{h[1]}` | {h[2]} | {h[3]} | "
                     f"{'✅ ' + h[5] if h[5] == '安全' else '⚠️ ' + h[5]} | {h[6]} |")
        L.append("")
        L.append("### 命中原文\n")
        L.append("```")
        for n, h in enumerate(hits, 1):
            L.append(f"{n}. {h[0]}:{h[1]}")
            L.append(f"   {h[4][:160]}")
        L.append("```\n")

    L.append("## 结论\n")
    if not need:
        L.append(f"**未发现真实凭据泄漏。** 命中 {len(hits)} 处，"
                 f"**全部经逐条判定为安全**（从环境变量/文件读取，或为占位符与本地默认值）。\n")
    else:
        L.append(f"**有 {len(need)} 处需人工确认**，见上表。\n")

    L.append("## ★ 方法论要求（为什么不能只报「无命中」）\n")
    L.append("| 必须报告 | 理由 |")
    L.append("|---|---|")
    L.append("| **扫描模式** | 别人要能复现你的扫描 |")
    L.append("| **命中条数** | 「没找到」≠「确认没有」 |")
    L.append("| **逐条判定** | `os.environ.get(...)` 是**正确做法**，不判定就分不清安全与泄漏 |")
    L.append("| **局限声明** | 本扫描只看工作区文件，**不看 git 历史**；历史里的凭据需另查 |")

    out = "\n".join(L)
    if args.out:
        open(args.out, "w", encoding="utf-8", newline="\n").write(out)
        print(f"  ✅ 已写入 {args.out}（{len(out)} 字符）")
    else:
        print(out)
    print(f"\n  命中 {len(hits)} 处：安全 {len(safe)} / 需确认 {len(need)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
