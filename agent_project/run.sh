#!/bin/bash
# ============================================================
# 简历优化 Agent v2.0 · 一键启动脚本
# 启动前自动清理 .pyc 缓存 + 禁止生成新缓存
# 用法：bash run.sh
# ============================================================
set -e

cd "$(dirname "$0")"

# 清除历史缓存
echo "🧹 清理 Python 缓存…"
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
find . -type f -name "*.pyc" -delete 2>/dev/null

# 彻底禁止生成 .pyc（子进程也会继承）
export PYTHONDONTWRITEBYTECODE=1

# 杀掉旧进程
OLD_PID=$(netstat -ano 2>/dev/null | grep ':8502' | grep 'LISTENING' | awk '{print $NF}' | head -1)
if [ -n "$OLD_PID" ]; then
    echo "🔪 结束旧的 Streamlit 进程 (PID: $OLD_PID)…"
    taskkill //PID "$OLD_PID" //F 2>/dev/null
    sleep 1
fi

echo "🚀 启动简历优化 Agent…"
echo "   浏览器访问：http://localhost:8502"
echo "   停止：Ctrl+C"
echo ""

exec python -m streamlit run app.py --server.port 8502
