#!/usr/bin/env bash
# =============================================================================
#  端到端场景批量验证
#  用途：对多个代表性场景调用智能体，收集完整证据链
# =============================================================================
set -uo pipefail

BASE="${BASE:-http://127.0.0.1:3000}"
EMAIL="${EMAIL:-admin@<example-domain>}"
PASS="${PASS:-<ADMIN_PASSWORD>}"
AGENT_ID="${AGENT_ID:-2}"
OUTDIR="${OUTDIR:-/root/e2e_results}"

mkdir -p "$OUTDIR"

# ---------- 1. 登录 ----------
echo "=== 登录 ==="
curl -s -X POST "$BASE/api/user/signin" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASS\"}" \
  -c /tmp/ck.txt -o /dev/null
TOK=$(grep 'nexent_access_token' /tmp/ck.txt | awk '{print $NF}')
echo "  token 长度: ${#TOK}"

# ---------- 2. 场景清单 ----------
# 覆盖：典型正例 / 不同密度类型 / 边界值 / 拒答 / 禁忌
declare -a CASES=(
  "S1|典型正例 mGGN≤8mm|一位55岁男性，8mm混合磨玻璃结节，实性成分2mm，吸烟30年，该怎么随访？"
  "S2|纯磨玻璃 pGGN 5~10mm|女，48岁，右肺上叶6mm纯磨玻璃结节，无吸烟史，该如何处理？"
  "S3|实性结节≤8mm 无危险因素|患者45岁，7mm实性结节，无吸烟史，无其他危险因素，怎么随访？"
  "S4|实性结节≤8mm 有危险因素|男性，58岁，5mm实性结节，吸烟25年，随访方案？"
  "S5|mGGN>8mm|男，62岁，15mm混杂性磨玻璃结节，吸烟40年，有毛刺征，如何处理？"
  "S6|拒答-信息不足|我有肺结节，该怎么办？"
  "S7|拒答-仅有密度|体检发现磨玻璃结节，需要处理吗？"
  "S8|禁忌场景|一位55岁男性，8mm混合磨玻璃结节，实性成分2mm，能否做PET-CT评估？"
)

echo ""
echo "=== 开始批量验证（共 ${#CASES[@]} 个场景）==="

for item in "${CASES[@]}"; do
  ID="${item%%|*}"
  REST="${item#*|}"
  LABEL="${REST%%|*}"
  QUERY="${REST#*|}"

  echo ""
  echo "----------------------------------------"
  echo "[$ID] $LABEL"
  echo "  问题: $QUERY"

  # 构造请求体（用 python 保证 UTF-8 与转义正确）
  python3 - "$QUERY" "$AGENT_ID" > /tmp/req_body.json <<'PY'
import json, sys
print(json.dumps({
    "query": sys.argv[1],
    "agent_id": int(sys.argv[2]),
    "version_no": 0,
    "is_debug": True,
}, ensure_ascii=False))
PY

  OUT="$OUTDIR/${ID}.txt"
  curl -s -N --max-time 240 -X POST "$BASE/api/agent/run" \
    -H "Authorization: Bearer $TOK" \
    -H "Content-Type: application/json" \
    --data-binary @/tmp/req_body.json > "$OUT" 2>&1

  SIZE=$(wc -c < "$OUT")
  echo "  响应: $SIZE 字节"

  # 快速统计
  TOOLS=$(grep -o '"type": *"tool"' "$OUT" 2>/dev/null | wc -l)
  echo "  工具调用事件: $TOOLS"

  # 保存问题文本供后续解析
  echo "$QUERY" > "$OUTDIR/${ID}.question.txt"
done

echo ""
echo "========================================"
echo "  批量验证完成"
echo "  结果目录: $OUTDIR"
ls -la "$OUTDIR"/*.txt 2>/dev/null | awk '{printf "    %-40s %s 字节\n", $9, $5}'
