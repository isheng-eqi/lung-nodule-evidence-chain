#!/usr/bin/env bash
# =============================================================================
#  肺结节知识图谱 MCP 服务 · 启停脚本
#  用于在 nexent-mcp 容器内启动/停止/检查 MCP Server
# =============================================================================
set -uo pipefail

CONTAINER="${MCP_CONTAINER:-nexent-mcp}"
PORT="${MCP_PORT:-8020}"
SRC="/mnt/c/Users/HI/Desktop/ict2026/mcp-server/kg_mcp_server.py"
DST="/tmp/kg_mcp_server.py"
LOG="/tmp/mcp.log"

info() { echo -e "\033[36m[MCP]\033[0m $*"; }
ok()   { echo -e "\033[32m  ✅\033[0m $*"; }
err()  { echo -e "\033[31m  ❌\033[0m $*"; }

# 杀掉容器内所有 kg_mcp_server 进程（容器内无 pkill，用 /proc 遍历）
kill_all() {
  docker exec "$CONTAINER" python - <<'PY'
import os, glob, signal, time
killed = []
for p in glob.glob('/proc/[0-9]*'):
    try:
        pid = int(p.split('/')[-1])
        cmd = open(f'{p}/cmdline', 'rb').read().decode('utf-8', 'replace').replace('\x00', ' ')
        if 'kg_mcp_server' in cmd and pid != os.getpid():
            os.kill(pid, signal.SIGKILL)
            killed.append(pid)
    except Exception:
        pass
time.sleep(1)
print('  killed:', killed if killed else 'none')
PY
}

case "${1:-start}" in
  start)
    info "部署脚本到容器"
    docker cp "$SRC" "$CONTAINER:$DST" >/dev/null 2>&1 || { err "复制失败，检查路径"; exit 1; }
    docker exec "$CONTAINER" python -m py_compile "$DST" || { err "语法错误"; exit 1; }
    ok "语法检查通过"

    info "停止已有实例"
    kill_all
    sleep 2

    info "启动 HTTP 服务 (端口 $PORT)"
    docker exec -d "$CONTAINER" sh -c "cd /tmp && nohup python kg_mcp_server.py --transport http --host 0.0.0.0 --port $PORT > $LOG 2>&1"
    sleep 8

    docker exec "$CONTAINER" sh -c "tail -4 $LOG"
    info "健康检查"
    docker exec "$CONTAINER" python - "$PORT" <<'PY'
import socket, sys
port = int(sys.argv[1])
s = socket.socket(); s.settimeout(3)
print('  port', port, '->', 'LISTENING' if s.connect_ex(('127.0.0.1', port)) == 0 else 'DOWN')
s.close()
PY
    ;;
  stop)
    info "停止 MCP 服务"
    kill_all
    ok "已停止"
    ;;
  status)
    info "状态检查"
    docker exec "$CONTAINER" python - "$PORT" <<'PY'
import socket, sys, glob, os
port = int(sys.argv[1])
s = socket.socket(); s.settimeout(3)
print('  port', port, '->', 'LISTENING' if s.connect_ex(('127.0.0.1', port)) == 0 else 'DOWN')
s.close()
n = 0
for p in glob.glob('/proc/[0-9]*'):
    try:
        cmd = open(f'{p}/cmdline', 'rb').read().decode('utf-8','replace').replace('\x00',' ')
        if 'kg_mcp_server' in cmd and 'python' in cmd:
            n += 1
    except Exception:
        pass
print('  processes:', n)
PY
    info "Nexent 侧连通性"
    docker exec nexent-config python - <<'PY'
import asyncio
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
async def go():
    try:
        async with Client(transport=StreamableHttpTransport(
                url='http://nexent-mcp:8020/mcp', headers={})) as c:
            tools = await c.list_tools()
            print(f'  ✅ Nexent 可连接，工具数 {len(tools)}')
    except Exception as e:
        print('  ❌', type(e).__name__, str(e)[:120])
asyncio.run(go())
PY
    ;;
  test)
    info "端到端工具调用测试"
    docker exec nexent-config python - <<'PY'
import asyncio
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
async def go():
    async with Client(transport=StreamableHttpTransport(
            url='http://nexent-mcp:8020/mcp', headers={})) as c:
        r = await c.call_tool('kg_consult_decision',
            {'description': '55岁男性，8mm混合磨玻璃结节，实性成分2mm，吸烟30年'})
        sc = r.structured_content or {}
        print('  条款  :', sc.get('clause'), sc.get('clause_title'))
        print('  强度  :', sc.get('strength'))
        print('  随访  :', sc.get('follow_up'))
        print('  推理跳:', len(sc.get('chain', [])))
        print('  可溯源:', sc.get('traceable'))
asyncio.run(go())
PY
    ;;
  *)
    echo "用法: $0 {start|stop|status|test}"
    exit 1
    ;;
esac
