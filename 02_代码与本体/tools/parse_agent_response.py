#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agent 响应解析器
================================================================

Nexent 智能体的流式响应为 SSE 格式（大量 `data: {...}` 行），
其中混有思考过程、工具调用、执行日志等多种事件。

本工具抽取：
  1. 最终回答文本（answer）
  2. 工具调用记录（tools）
  3. 思考过程摘要（thinking）
  4. 关键指标（工具调用次数、条款引用数、耗时）

用法：
    python3 parse_agent_response.py --input resp.txt --out answer.md
    python3 parse_agent_response.py --input resp.txt --json out.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any


def load_events(path: str) -> list[dict[str, Any]]:
    """从 SSE 文本中解析所有 JSON 事件。"""
    events: list[dict[str, Any]] = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if not payload or payload in ("[DONE]", "null"):
                continue
            try:
                obj = json.loads(payload)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                events.append(obj)
    return events


def _unescape(s: str) -> str:
    """处理双层转义的换行与引号。"""
    return (s.replace("\\r\\n", "\n")
             .replace("\\n", "\n")
             .replace('\\"', '"')
             .replace("\\\\", "\\"))


def extract(events: list[dict[str, Any]]) -> dict[str, Any]:
    """从事件流中抽取结构化信息。"""
    tools: list[dict[str, Any]] = []
    answers: list[str] = []
    thinking_chunks: list[str] = []
    event_types: dict[str, int] = {}
    token_info: dict[str, Any] = {}
    durations: list[float] = []
    step_count = 0

    for ev in events:
        t = ev.get("type", "")
        event_types[t] = event_types.get(t, 0) + 1
        content = ev.get("content")

        if t == "tool":
            # 工具事件格式（v1.1 修正）：
            #   {"type":"tool", "content":"", "tool_name":"kg_consult_decision",
            #    "tool_arguments":{...}, "tool_call_id":"..."}
            # 工具名与参数是**顶层字段**，不在 content 中。
            nm = ev.get("tool_name") or ev.get("name")
            if not nm and content:
                try:
                    to = json.loads(content) if isinstance(content, str) else content
                    if isinstance(to, dict):
                        nm = to.get("name") or to.get("tool_name")
                        to = {"name": nm, "arguments": to.get("arguments")}
                        tools.append(to)
                except Exception:
                    pass
            if nm:
                tools.append({
                    "name": nm,
                    "arguments": ev.get("tool_arguments") or {},
                    "call_id": ev.get("tool_call_id", ""),
                })

        elif t in ("model_output", "answer", "final_answer"):
            if isinstance(content, str) and content.strip():
                txt = _unescape(content)
                # 排除内部标记
                if not txt.startswith("<") and len(txt) > 50:
                    answers.append(txt)

        elif t in ("model_output_thinking", "model_output_deep_thinking"):
            if isinstance(content, str):
                thinking_chunks.append(content)

        elif t == "token_count":
            try:
                tk = json.loads(content) if isinstance(content, str) else content
                if isinstance(tk, dict):
                    token_info = tk
                    durations.append(float(tk.get("duration") or 0))
            except Exception:
                pass

        elif t == "step_count":
            if isinstance(content, str):
                m = re.search(r"步骤\s*(\d+)", content)
                if m:
                    step_count = max(step_count, int(m.group(1)))

    # 选最长的答案段落作为最终回答
    final = ""
    if answers:
        final = max(answers, key=len)

    # 统计工具调用
    tool_names: dict[str, int] = {}
    for t in tools:
        nm = (t.get("name") or t.get("tool_name")
              or t.get("function", {}).get("name") or "unknown")
        tool_names[nm] = tool_names.get(nm, 0) + 1

    # 条款引用统计
    clauses = sorted({int(x) for x in re.findall(r"【推荐意见\s*(\d+)\s*】", final)})

    return {
        "final_answer": final,
        "answer_chars": len(final),
        "tools_called": tool_names,
        "tool_call_total": sum(tool_names.values()),
        "tool_calls_detail": [
            {"name": x.get("name"), "arguments": x.get("arguments")}
            for x in tools
        ],
        "thinking_chars": sum(len(x) for x in thinking_chunks),
        "event_types": event_types,
        "token_info": token_info,
        "total_duration_sec": round(sum(durations), 2),
        "step_count": step_count,
        "clauses_cited": clauses,
        "clause_citation_count": len(clauses),
        "has_disclaimer": ("仅供临床参考" in final or "不替代医生" in final),
        "has_refusal": ("未覆盖" in final or "上级医院会诊" in final),
        "has_contraindication": ("不推荐" in final or "不适用" in final),
    }


def to_markdown(info: dict[str, Any], question: str = "") -> str:
    lines = ["# 智能体问答记录", ""]
    if question:
        lines += ["## 提问", "", question, ""]
    lines += [
        "## 回答", "", info["final_answer"] or "（未提取到回答）", "",
        "---", "", "## 调用统计", "",
        "| 指标 | 值 |", "|---|---|",
        f"| 工具调用总次数 | {info['tool_call_total']} |",
    ]
    for nm, cnt in sorted(info["tools_called"].items(), key=lambda x: -x[1]):
        lines.append(f"| ├─ `{nm}` | {cnt} |")
    lines += [
        f"| 引用条款数 | {info['clause_citation_count']} |",
        f"| 引用条款 | {', '.join('推荐意见'+str(c) for c in info['clauses_cited']) or '无'} |",
        f"| 回答字数 | {info['answer_chars']} |",
        f"| 思考字数 | {info['thinking_chars']} |",
        f"| 推理步数 | {info['step_count']} |",
        f"| 含免责声明 | {'是' if info['has_disclaimer'] else '否'} |",
        f"| 含禁忌提示 | {'是' if info['has_contraindication'] else '否'} |",
        f"| 含未覆盖提示 | {'是' if info['has_refusal'] else '否'} |",
    ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="解析 Nexent 智能体响应")
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", default="")
    ap.add_argument("--json", default="")
    ap.add_argument("--question", default="")
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args()

    if not os.path.exists(args.input):
        print(f"[ERROR] 文件不存在: {args.input}", file=sys.stderr)
        return 2

    events = load_events(args.input)
    info = extract(events)

    if args.report:
        print("=" * 68)
        print("  智能体响应解析报告")
        print("=" * 68)
        print(f"  事件总数        : {len(events)}")
        print(f"  工具调用总次数  : {info['tool_call_total']}")
        for nm, cnt in sorted(info["tools_called"].items(), key=lambda x: -x[1]):
            print(f"    ├─ {nm:28s} {cnt} 次")
        print(f"  引用条款数      : {info['clause_citation_count']}"
              f"  {', '.join('推荐意见'+str(c) for c in info['clauses_cited'])}")
        print(f"  回答字数        : {info['answer_chars']}")
        print(f"  思考字数        : {info['thinking_chars']}")
        print(f"  推理步数        : {info['step_count']}")
        print(f"  含免责声明      : {'是' if info['has_disclaimer'] else '否'}")
        print(f"  含禁忌提示      : {'是' if info['has_contraindication'] else '否'}")
        print(f"  含未覆盖提示    : {'是' if info['has_refusal'] else '否'}")
        print("-" * 68)
        print("  事件类型分布（前 10）:")
        for k, v in sorted(info["event_types"].items(), key=lambda x: -x[1])[:10]:
            print(f"    {k:32s} {v}")
        print("=" * 68)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(to_markdown(info, args.question))
        print(f"\n  Markdown 已保存: {args.out}")

    if args.json:
        # 去掉超大的原始工具事件以控制体积
        slim = dict(info)
        slim.pop("tool_events_raw", None)
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(slim, f, ensure_ascii=False, indent=2)
        print(f"  JSON 已保存: {args.json}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
