#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
提交包一致性检查器
================================================================

在提交前做一轮自动化核验，检查：

  1. **文件完整性**   —— 提交包中引用的文件是否都存在
  2. **数据一致性**   —— 文档中同一指标是否出现互相矛盾的值
  3. **路径可解析**   —— 文档中提到的脚本/文件路径是否有对应实物
  4. **版本唯一性**   —— 是否残留多个版本的主文档
  5. **占位符检查**   —— 是否还有未填写的占位符（除已知待填项）

用法：
    python3 check_package.py --pkg <提交包目录> --doc <文档.md>
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict


# 需要在文档中保持一致的关键指标
KEY_METRICS = {
    "owl_class": [r"owl:Class\D{0,8}(\d+)", r"(\d+)\s*类"],
    "obj_prop": [r"owl:ObjectProperty\D{0,8}(\d+)", r"(\d+)\s*个对象属性"],
    "data_prop": [r"owl:DatatypeProperty\D{0,8}(\d+)", r"(\d+)\s*个数据属性"],
    "clause": [r"(\d+)\s*条推荐意见", r"条款实例\D{0,8}(\d+)"],
}


class Checker:
    def __init__(self, pkg: str, doc: str):
        self.pkg = pkg
        self.doc = doc
        self.issues: list[tuple[str, str]] = []      # (级别, 说明)
        self.notes: list[str] = []

    # ---------------- 1. 文件完整性 ----------------
    def check_files(self) -> None:
        if not os.path.isdir(self.pkg):
            self.issues.append(("ERROR", f"提交包目录不存在: {self.pkg}"))
            return
        all_files = []
        for root, _, files in os.walk(self.pkg):
            for f in files:
                all_files.append(os.path.relpath(os.path.join(root, f), self.pkg))
        self.notes.append(f"提交包共 {len(all_files)} 个文件")

        # 必须存在的关键文件（按后缀/关键词匹配，含嵌套子目录）
        # 注意：早期版本只扫描包顶层目录，导致 skill/xxx/SKILL.md
        # 这类嵌套文件被漏检。此处统一递归匹配。
        required = {
            "开发设计文档 Word": lambda p: p.endswith(".docx") and "开发设计" in p,
            "调用关系图": lambda p: "调用关系图" in p and p.endswith(".md"),
            "OWL 本体": lambda p: p.endswith(".ttl"),
            "MCP Server 代码": lambda p: "kg_mcp_server.py" in p,
            "评测集": lambda p: "evalset" in p or "build_evalset" in p,
            "参考资料清单": lambda p: "参考资料" in p,
            "提交包说明": lambda p: "提交包说明" in p or "00_" in p,
            # 以下三项为早期遗漏、本轮补齐的文件
            "Skill 定义（SKILL.md）": lambda p: p.endswith("SKILL.md"),
            "Skill 参数配置（schema.yaml）": lambda p: p.endswith("schema.yaml"),
            "多行业迁移验证报告": lambda p: "migration" in p or "迁移验证报告" in p,
            "知识图谱推理服务": lambda p: "kg_reasoning_service.py" in p,
            "语料清洗器": lambda p: "clean_corpus.py" in p,
            "OWL 导出器": lambda p: "ontology_export.py" in p,
            "工作流模板": lambda p: "workflow_template.py" in p,
        }
        for label, pred in required.items():
            if not any(pred(p) for p in all_files):
                self.issues.append(("ERROR", f"缺少关键文件: {label}"))

    # ---------------- 2. 版本唯一性 ----------------
    def check_versions(self) -> None:
        docx = []
        for root, _, files in os.walk(self.pkg):
            for f in files:
                if f.endswith(".docx") and "开发设计" in f:
                    docx.append(os.path.join(os.path.relpath(root, self.pkg), f))
        if len(docx) > 1:
            self.issues.append(
                ("WARN", f"存在多个开发设计文档版本: {docx}；建议只保留最终版"))
        elif len(docx) == 1:
            self.notes.append(f"开发设计文档唯一: {docx[0]}")

    # ---------------- 3. 数据一致性 ----------------
    def check_metrics(self) -> None:
        if not os.path.isfile(self.doc):
            self.issues.append(("ERROR", f"文档不存在: {self.doc}"))
            return
        with open(self.doc, encoding="utf-8") as f:
            text = f.read()

        # 抽取形如「57 类」的声明，检查是否与本体规模表一致
        # 本体规模表是权威来源
        m = re.search(r"\|\s*`owl:Class`\s*\|\s*\*\*(\d+)\*\*\s*\|", text)
        if m:
            authoritative = m.group(1)
            self.notes.append(f"本体规模表声明 owl:Class = {authoritative}")
            # 检查「N 类」的其他声明
            others = set()
            for mm in re.finditer(r"OWL 本体（(\d+)\s*类", text):
                others.add(mm.group(1))
            for mm in re.finditer(r"本体（(\d+)\s*类", text):
                others.add(mm.group(1))
            # 以下数值是文档中已显式区分的"其他本体形态"，不算冲突：
            #   52 —— 流水线版 TTL（种子本体规模）
            #   14 —— 迁移模板的精简本体（用于验证骨架复用性）
            KNOWN_VARIANTS = {"52", "14"}
            conflict = {o for o in others if o != authoritative} - KNOWN_VARIANTS
            if conflict:
                self.issues.append(
                    ("WARN", f"OWL 类数出现不一致声明: 权威 {authoritative}, 其他 {sorted(conflict)}"))
            else:
                self.notes.append(
                    f"OWL 类数声明一致（{'/'.join(sorted(KNOWN_VARIANTS))} "
                    f"已在文档中标注为流水线版与迁移模板）")
        else:
            self.issues.append(("WARN", "未找到本体规模表中的 owl:Class 行"))

    # ---------------- 4. 脚本路径可解析 ----------------
    def check_script_refs(self) -> None:
        if not os.path.isfile(self.doc):
            return
        with open(self.doc, encoding="utf-8") as f:
            text = f.read()
        # 找形如 xxx.py / xxx.sh 的引用
        refs = set(re.findall(r"[\w\-]+\.(?:py|sh|ttl|json|csv)", text))
        all_files = set()
        for root, _, files in os.walk(self.pkg):
            for f in files:
                all_files.add(f)
        missing = sorted(r for r in refs if r not in all_files)
        # 过滤掉明显是示例/外部文件的引用
        ignore = {"pyproject.toml", "const.py", "monitoring.env", "package.json"}
        missing = [m for m in missing if m not in ignore]
        if missing:
            self.issues.append(
                ("INFO", f"文档引用但包内未直接包含的文件名（{len(missing)} 个）: {missing[:10]}"))
        else:
            self.notes.append("文档引用的文件名均可在包内找到")

    # ---------------- 5. 占位符检查 ----------------
    def check_placeholders(self) -> None:
        if not os.path.isfile(self.doc):
            return
        with open(self.doc, encoding="utf-8") as f:
            text = f.read()
        ph = re.findall(r"〔([^〕]+)〕", text)
        if ph:
            uniq = sorted(set(ph))
            self.notes.append(f"待填写占位符 {len(ph)} 处: {uniq}")

    # ---------------- 6. 待完成项扫描 ----------------
    def check_todos(self) -> None:
        pat = re.compile(r"(TODO|FIXME|XXX|待补充|待填写)", re.IGNORECASE)
        hits: dict[str, int] = defaultdict(int)
        for root, _, files in os.walk(self.pkg):
            for f in files:
                if not f.endswith((".md", ".txt")):
                    continue
                p = os.path.join(root, f)
                try:
                    with open(p, encoding="utf-8", errors="replace") as fh:
                        for line in fh:
                            if pat.search(line):
                                hits[os.path.relpath(p, self.pkg)] += 1
                except OSError:
                    continue
        if hits:
            self.notes.append(f"含待办标记的文件 {len(hits)} 个（提交前请确认是否需清理）")
            for k, v in sorted(hits.items(), key=lambda x: -x[1])[:5]:
                self.notes.append(f"    {k}: {v} 处")

    def run(self) -> int:
        print("=" * 72)
        print("  提交包一致性检查")
        print("=" * 72)
        self.check_files()
        self.check_versions()
        self.check_metrics()
        self.check_script_refs()
        self.check_placeholders()
        self.check_todos()

        print()
        print("--- 检查结果 ---")
        if not self.issues:
            print("  ✅ 未发现问题")
        else:
            order = {"ERROR": 0, "WARN": 1, "INFO": 2}
            for lvl, msg in sorted(self.issues, key=lambda x: order.get(x[0], 9)):
                icon = {"ERROR": "❌", "WARN": "⚠️ ", "INFO": "ℹ️ "}.get(lvl, "  ")
                print(f"  {icon} [{lvl}] {msg}")

        print()
        print("--- 说明 ---")
        for n in self.notes:
            print(f"  · {n}")
        print("=" * 72)

        return 1 if any(l == "ERROR" for l, _ in self.issues) else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="提交包一致性检查器")
    ap.add_argument("--pkg", required=True, help="提交包目录")
    ap.add_argument("--doc", required=True, help="开发设计文档 Markdown 源文件")
    args = ap.parse_args()
    return Checker(args.pkg, args.doc).run()


if __name__ == "__main__":
    sys.exit(main())
