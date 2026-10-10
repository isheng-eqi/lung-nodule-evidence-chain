#!/usr/bin/env bash
# =============================================================================
#  端到端演示 · 可复现调用脚本
#  用途：一次命令完成"检索-推理双驱动"的完整验证
# =============================================================================
set -uo pipefail

BASE="${BASE:-http://127.0.0.1:3000}"
EMAIL="${EMAIL:-admin@<example-domain>}"
PASS="${PASS:-<ADMIN_PASSWORD>}"
AGENT_ID="${AGENT_ID:-2}"
QUERY="${QUERY:-一位55岁男性，8mm混合磨玻璃结节，实性成分2mm，吸烟30年，该怎么随访？}"

echo "=== 1. 登录获取 token ==="
TOKEN=$(curl -s -X POST "$BASE/api/user/signin" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASS\"}" \
  -c /tmp/ck.txt -o /dev/null -w "%{http_code}")
grep -o 'nexent_access_token[[:space:]]*[^[:space:]]*' /tmp/ck.txt | awk '{print $2}' > /tmp/tok.txt
TOK=$(cat /tmp/tok.txt)
echo "  token 长度: ${#TOK}"

echo ""
echo "=== 2. 调用智能体（is_debug=true 暴露真实错误）==="
python3 - "$QUERY" "$AGENT_ID" > /tmp/body.json <<'PY'
import json, sys
print(json.dumps({"query": sys.argv[1], "agent_id": int(sys.argv[2]),
                  "version_no": 0, "is_debug": True}, ensure_ascii=False))
PY

curl -s -N --max-time 240 -X POST "$BASE/api/agent/run" \
  -H "Authorization: Bearer $TOK" \
  -H "Content-Type: application/json" \
  --data-binary @/tmp/body.json > /tmp/e2e_out.txt 2>&1

SIZE=$(wc -c < /tmp/e2e_out.txt)
echo "  响应大小: $SIZE 字节"

echo ""
echo "=== 3. 关键证据统计 ==="
for kw in kg_consult_decision kg_get_clause knowledge_base_search 推荐意见14 推荐意见 PET-CT "3、6、12"; do
  N=$(grep -o "$kw" /tmp/e2e_out.txt 2>/dev/null | wc -l)
  MARK=$([ "$N" -gt 0 ] && echo "✅" || echo "  ")
  printf "  %s %-24s %s 次\n" "$MARK" "$kw" "$N"
done

echo ""
echo "=== 4. 事件类型统计 ==="
grep -o '"type": *"[a-z_]*"' /tmp/e2e_out.txt 2>/dev/null | sed 's/.*"\([a-z_]*\)"/\1/' | sort | uniq -c | sort -rn | head -8

echo ""
echo "  完整响应已保存: /tmp/e2e_out.txt"