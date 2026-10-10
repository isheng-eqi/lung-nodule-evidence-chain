#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 3 份附加规范灌入 Nexent 知识库（ES 索引）
================================================================

背景
----
独立审计指出：
  「L3 证据层只有 1 份文档 —— 知识库内容 = 《2024 共识》全文，17 个分块。
    因此三条 `knowledge_base_search` 结果**全部来自同一份文档** ——
    所谓"检索-推理双驱动"里的"检索"半边，在跨文档意义上是空的。」

本脚本用**平台自身的知识库 API**（而非绕过平台直写 ES）把另外 3 份文档入库：
  1. 筛查指南 2025（LVCT 筛查指南 2025 年版）
  2. 筛查指南 2023（同指南 2023 年版，用于版本对照）
  3. 共识 2025（肺癌筛查及肺结节健康管理专家共识 2025 版）

流程（与平台前端一致）
----
  POST /file/upload   → 上传到 MinIO，返回 object path
  POST /file/process  → 解析 + 分块 + 向量化 + 写入 ES 索引

用法
----
    python3 ingest_knowledge_base.py \
        --corpus-dir corpus/ \
        --index 4-1fd943cfa3c044419a587e642b005759 \
        --token-file /root/.tok
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.request
import uuid


CONFIG_API = "http://127.0.0.1:5010"


def _post_multipart(url: str, token: str, filepath: str,
                    fields: dict[str, str]) -> dict:
    """最小 multipart/form-data 上传（不依赖 requests）。"""
    boundary = "----kb" + uuid.uuid4().hex
    fname = os.path.basename(filepath)
    ctype = mimetypes.guess_type(fname)[0] or "text/plain"
    body = bytearray()
    for k, v in fields.items():
        body += f"--{boundary}\r\n".encode()
        body += f'Content-Disposition: form-data; name="{k}"\r\n\r\n'.encode()
        body += f"{v}\r\n".encode()
    body += f"--{boundary}\r\n".encode()
    body += (f'Content-Disposition: form-data; name="file"; '
             f'filename="{fname}"\r\n').encode()
    body += f"Content-Type: {ctype}\r\n\r\n".encode()
    body += open(filepath, "rb").read()
    body += f"\r\n--{boundary}--\r\n".encode()

    req = urllib.request.Request(url, data=bytes(body), method="POST", headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    })
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read().decode())


def _post_json(url: str, token: str, payload: dict) -> dict:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), method="POST", headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        })
    with urllib.request.urlopen(req, timeout=900) as r:
        raw = r.read().decode()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"_raw": raw[:500]}


DOCS = [
    ("筛查指南2025_全文.txt", "中国肺癌低剂量CT筛查指南（2025年版）"),
    ("筛查指南2023_结构化版.txt", "中国肺癌低剂量CT筛查指南（2023年版）"),
    ("共识2025_全文.txt", "肺癌筛查及肺结节健康管理专家共识（2025版）"),
]


def main() -> int:
    ap = argparse.ArgumentParser(description="知识库灌库")
    ap.add_argument("--corpus-dir", required=True)
    ap.add_argument("--index", required=True)
    ap.add_argument("--token-file", default="/root/.tok")
    ap.add_argument("--out", default="kb_ingest_report.json")
    args = ap.parse_args()

    token = open(args.token_file, encoding="utf-8").read().strip()
    print("=" * 78)
    print("  知识库灌库（3 份附加规范）")
    print("=" * 78)
    print(f"  目标索引: {args.index}")
    print(f"  Token   : {len(token)} 字符")
    print()

    report = {"index_name": args.index, "documents": [], "errors": []}

    for fname, title in DOCS:
        p = os.path.join(args.corpus_dir, fname)
        if not os.path.exists(p):
            print(f"  ✗ {fname} 不存在，跳过")
            report["errors"].append({"file": fname, "error": "NOT_FOUND"})
            continue

        size = os.path.getsize(p)
        print(f"  ── {title} ({size:,} 字节) ──")

        # 1. 上传
        try:
            up = _post_multipart(f"{CONFIG_API}/file/upload", token, p,
                                 {"destination": "minio"})
        except urllib.error.HTTPError as e:
            msg = e.read().decode()[:200]
            print(f"     上传失败 HTTP {e.code}: {msg}")
            report["errors"].append({"file": fname, "stage": "upload",
                                     "error": msg})
            continue

        paths = up.get("uploaded_file_paths") or []
        if not paths:
            print(f"     上传无返回路径: {str(up)[:160]}")
            report["errors"].append({"file": fname, "stage": "upload",
                                     "error": str(up)[:200]})
            continue
        obj = paths[0]
        print(f"     ① 已上传: {obj}")

        # 2. 解析入库
        # ⚠️ 字典键名必须是 `path_or_url`（不是 object_name）——
        #    这是 `/file/process` 的约定（见 apps/file_management_app.py:
        #    "List of dicts, each with path_or_url and filename"），
        #    config 侧再取它做 data-process 的 `source` 字段。
        #    传错键名会得到 HTTP 500 "Data process service failed"
        #    （真实原因被吞掉，data-process 侧报 source 为 null）。
        payload = {
            "files": [{
                "path_or_url": obj,
                "filename": fname,
            }],
            "index_name": args.index,
            "destination": "minio",
            "chunking_strategy": "basic",
        }
        try:
            pr = _post_json(f"{CONFIG_API}/file/process", token, payload)
        except urllib.error.HTTPError as e:
            msg = e.read().decode()[:300]
            print(f"     ② 入库失败 HTTP {e.code}: {msg}")
            report["errors"].append({"file": fname, "stage": "process",
                                     "error": msg})
            continue

        print(f"     ② 已提交入库: {str(pr)[:180]}")
        report["documents"].append({
            "file": fname, "title": title, "object_name": obj,
            "size_bytes": size, "process_response": pr,
        })
        time.sleep(2)

    print()
    print("=" * 78)
    print(f"  成功: {len(report['documents'])} / {len(DOCS)}")
    if report["errors"]:
        print(f"  失败: {len(report['errors'])}")
        for e in report["errors"]:
            print(f"    {e}")
    print("=" * 78)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"  报告已保存: {args.out}")
    return 0 if report["documents"] else 1


if __name__ == "__main__":
    sys.exit(main())
