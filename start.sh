#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON3="/opt/anaconda3/bin/python3"

# 自动查找 python3
if [ ! -x "$PYTHON3" ]; then
    PYTHON3=$(command -v python3)
fi

echo "🚀 Starting DataWorks Add Dimension Tool..."

# Rebuild frontend
echo "📦 Building frontend..."
cd "$SCRIPT_DIR/frontend"
npm run build 2>&1 | tail -5
cd "$SCRIPT_DIR"

# Kill any existing uvicorn on port 8080
lsof -ti:8080 2>/dev/null | xargs kill -9 2>/dev/null || true
sleep 1

cd "$SCRIPT_DIR/backend"

# 获取本机 IP（用于提示）
LOCAL_IP=$(ifconfig | grep -Eo 'inet (addr:)?[0-9.]+' | grep -v '127.0.0.1' | head -n1 | awk '{print $2}' | sed 's/addr://')

# 启动服务，绑定 0.0.0.0（允许局域网访问）
$PYTHON3 -m uvicorn main:app --host 0.0.0.0 --port 8080 &
BACKEND_PID=$!

echo ""
echo "✅ 本机访问:    http://localhost:8080"
echo "✅ 局域网访问:  http://${LOCAL_IP}:8080"
echo "✅ API 文档:    http://${LOCAL_IP}:8080/docs"
echo ""
echo "Press Ctrl+C to stop"

# Wait for interrupt
trap "echo ''; echo '🛑 Stopping...'; kill $BACKEND_PID 2>/dev/null || true; exit" INT
wait
