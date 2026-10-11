#!/usr/bin/env bash
# =============================================================================
#  肺结节知识图谱 MCP 服务 · 启停脚本
#  用于在 nexent-mcp 容器内启动/停止/检查 MCP Server
# =============================================================================
set -uo pipefail

CONTAINER="${MCP_CONTAINER:-nexent-mcp}"
PORT="${MCP_PORT:-8020}"
DST="/tmp/kg_mcp_server.py"
LOG="/tmp/mcp.log"
PYTMP="/tmp/_mcpctl_check.py"

# -----------------------------------------------------------------------------
# ★ 自动定位 kg_mcp_server.py（不再写死绝对路径）
#
#   历史问题：原先写的是
#       SRC="/mnt/c/Users/HI/Desktop/ict2026/mcp-server/kg_mcp_server.py"
#   但包被整理成 `提交包_初赛/02_代码与本体/mcp-server/` 之后该路径就不存在了。
#   现在按「本脚本所在目录」推导，两种布局都能命中：
#     · 提交包内： <pkg>/02_代码与本体/mcp-server/mcp-ctl.sh
#     · 开发目录： <repo>/mcp-server/mcp-ctl.sh
# -----------------------------------------------------------------------------
_here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC=""
for cand in \
    "${MCP_SRC:-}" \
    "$_here/kg_mcp_server.py" \
    "$_here/../../提交包/02_代码与本体/mcp-server/kg_mcp_server.py" \
    "$_here/mcp-server/kg_mcp_server.py" ; do
  if [ -n "$cand" ] && [ -f "$cand" ]; then SRC="$cand"; break; fi
done
if [ -z "$SRC" ]; then
  echo -e "\033[31m  ❌ 找不到 kg_mcp_server.py\033[0m"
  echo "     已尝试：$_here/kg_mcp_server.py"
  echo "               $_here/../../提交包/02_代码与本体/mcp-server/kg_mcp_server.py"
  echo "     可用 MCP_SRC=<路径> 显式指定。"
  exit 1
fi

info() { echo -e "\033[36m[MCP]\033[0m $*"; }
ok()   { echo -e "\033[32m  ✅\033[0m $*"; }
err()  { echo -e "\033[31m  ❌\033[0m $*"; }

# -----------------------------------------------------------------------------
# ★ 在容器内执行 python：**先把代码写成文件，再执行**
#
#   踩过的坑：原先用 `docker exec "$CONTAINER" python - <<'PY' ... PY`
#   实测 **stdin 不可靠** —— heredoc 版本完全无输出，而内联 `python -c`
#   正常。这类静默失败最难查。改成写文件执行，不依赖 stdin。
# -----------------------------------------------------------------------------
run_py() {   # 用法：run_py <<'PY' ... PY
  local tmp
  tmp="$(mktemp)"
  cat > "$tmp"
  docker cp "$tmp" "$CONTAINER:$PYTMP" >/dev/null 2>&1
  rm -f "$tmp"
  docker exec "$CONTAINER" python "$PYTMP"
}

# TCP 探测：注意 —— **TIME_WAIT 期间端口仍可连**，
# 所以本函数只用于「结果验证」，不能单独当作「就绪判据」。
probe() {
  docker exec "$CONTAINER" python -c "
import socket, sys
s = socket.socket(); s.settimeout(3)
sys.exit(0 if s.connect_ex(('127.0.0.1', $PORT)) == 0 else 1)
" 2>/dev/null
}

kill_all() {
  run_py <<'PY'
import os, glob, signal, time
killed, seen = [], []
for p in glob.glob('/proc/[0-9]*'):
    try:
        pid = int(p.split('/')[-1])
        # 注意：读 cmdline 时若文件为空（已故进程），不能当作"无匹配"
        cmd = open(f'{p}/cmdline', 'rb').read().decode('utf-8', 'replace').replace('\x00', ' ').strip()
        seen.append((pid, cmd))
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
    info "源文件: $SRC"
    info "部署到容器"
    docker cp "$SRC" "$CONTAINER:$DST" >/dev/null 2>&1 || { err "复制失败，检查路径与容器名"; exit 1; }
    docker exec "$CONTAINER" python -m py_compile "$DST" || { err "语法错误"; exit 1; }
    ok "语法检查通过"

    info "停止已有实例"
    kill_all

    # 清空日志 → 启动 → 轮询日志里的 "Uvicorn running"。
    # 只有新进程真起来了才会出现这一行 —— 这比探端口可靠。
    docker exec "$CONTAINER" sh -c ": > $LOG" 2>/dev/null || true
    sleep 1

    info "启动 HTTP 服务 (端口 $PORT)"
    docker exec -d "$CONTAINER" sh -c \
      "cd /tmp && nohup python kg_mcp_server.py --transport http --host 0.0.0.0 --port $PORT > $LOG 2>&1"

    info "等待启动完成（最多 30 秒）"
    ready=0
    for i in $(seq 1 15); do
      sleep 2
      if docker exec "$CONTAINER" sh -c "grep -q 'Uvicorn running' $LOG" 2>/dev/null; then
        ready=1; echo "  ✅ 启动完成（约 $((i*2)) 秒）"; break
      fi
      echo "  ${i}/15 启动中..."
    done

    if [ "$ready" -eq 1 ]; then
      docker exec "$CONTAINER" sh -c "grep -E 'Uvicorn running|Application startup complete' $LOG | tail -2" \
        | sed 's/^/    /'
      if probe; then ok "端口 $PORT 可连接"; else err "日志说启动了但端口不可连 —— 需排查"; exit 1; fi
      echo
      info "下一步：$0 status"
    else
      err "30 秒内未见 'Uvicorn running' —— 启动失败"
      echo "  ── 容器日志 ──"
      docker exec "$CONTAINER" sh -c "tail -20 $LOG" 2>&1 | sed 's/^/    /'
      echo "  ── 常见原因 ──"
      echo "    1. 端口 $PORT 被占用    → MCP_PORT=8021 $0 start"
      echo "    2. 容器未运行           → docker ps | grep $CONTAINER"
      echo "    3. 依赖缺失             → docker exec $CONTAINER python -c 'import mcp, fastmcp'"
      exit 1
    fi
    ;;

  stop)
    info "停止 MCP 服务"
    kill_all
    ok "已停止"
    ;;

  status)
    info "本地端口"
    if probe; then ok "端口 $PORT LISTENING"; else err "端口 $PORT DOWN —— 用 $0 start 启动"; fi

    info "容器内进程"
    run_py <<'PY'
import glob
n = 0
for p in glob.glob('/proc/[0-9]*'):
    try:
        cmd = open(f'{p}/cmdline', 'rb').read().decode('utf-8', 'replace').replace('\x00', ' ').strip()
        if 'kg_mcp_server' in cmd:
            print(f'   pid={p.split("/")[-1]}  {cmd[:90]}')
            n += 1
    except Exception:
        pass
print(f'   → {n} 个 kg_mcp_server 进程')
PY

    info "Nexent 侧连通性（从 nexent-config 容器视角）"
    local_tmp="$(mktemp)"
    cat > "$local_tmp" <<'PY'
import asyncio
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
async def go():
    try:
        async with Client(transport=StreamableHttpTransport(
                url='http://nexent-mcp:8020/mcp', headers={})) as c:
            tools = await c.list_tools()
            print(f'✅ Nexent 可连接，工具数 {len(tools)}')
            for t in tools:
                print(f'   · {t.name}')
    except Exception as e:
        print('❌', type(e).__name__, str(e)[:160])
asyncio.run(go())
PY
    docker cp "$local_tmp" nexent-config:/tmp/_nb_check.py >/dev/null 2>&1
    rm -f "$local_tmp"
    docker exec nexent-config python /tmp/_nb_check.py 2>&1 | grep -vE "AuthlibDeprecation|from authlib" | sed 's/^/  /'
    ;;

  test)
    info "端到端工具调用测试（真调 kg_consult_decision）"
    local_tmp="$(mktemp)"
    cat > "$local_tmp" <<'PY'
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
    docker cp "$local_tmp" nexent-config:/tmp/_nb_test.py >/dev/null 2>&1
    rm -f "$local_tmp"
    docker exec nexent-config python /tmp/_nb_test.py 2>&1 | grep -vE "AuthlibDeprecation|from authlib" | sed 's/^/  /'
    ;;

  *)
    echo "用法: $0 {start|stop|status|test}"
    echo
    echo "  start   部署并启动（自动等就绪，失败时打日志与常见原因）"
    echo "  stop    停止"
    echo "  status  端口 / 容器内进程 / Nexent 侧连通性与工具清单"
    echo "  test    真调一次 kg_consult_decision 验证端到端"
    echo
    echo "环境变量："
    echo "  MCP_CONTAINER  容器名（默认 nexent-mcp）"
    echo "  MCP_PORT       端口（默认 8020）"
    echo "  MCP_SRC        显式指定 kg_mcp_server.py 路径"
    exit 1
    ;;
esac
