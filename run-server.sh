#!/bin/bash
# 服务器端运行脚本（兼容旧环境）
# 前置条件：Python 3.11+ 和 Node.js 20+ 需手动安装

set -e

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON_VERSION="3.11"
NODE_VERSION="20"

echo "🚀 DataWorks 加维度工具 — 服务器端运行"

# ── 检查 Python ──────────────────────────────
if ! command -v python3 &> /dev/null || [ "$(python3 -c 'import sys; print(sys.version_info.major, sys.version_info.minor)' | tr ' ' '.')" != "$PYTHON_VERSION" ]; then
    echo "❌ 需要 Python $PYTHON_VERSION，当前版本:"
    python3 --version 2>/dev/null || echo "未找到 python3"
    echo ""
    echo "请安装 Python $PYTHON_VERSION:"
    echo "  conda: conda create -n dataworks python=$PYTHON_VERSION -y && conda activate dataworks"
    echo "  pyenv: pyenv install $PYTHON_VERSION && pyenv global $PYTHON_VERSION"
    exit 1
fi

# ── 检查 Node.js ─────────────────────────────
if ! command -v node &> /dev/null; then
    echo "❌ 未找到 Node.js"
    echo "请安装 Node.js $NODE_VERSION+: https://nodejs.org/"
    exit 1
fi

NODE_MAJOR=$(node -v | cut -d'v' -f2 | cut -d'.' -f1)
if [ "$NODE_MAJOR" -lt 20 ]; then
    echo "❌ Node.js 版本太旧: $(node -v)，需要 20+"
    echo "请升级: https://nodejs.org/"
    exit 1
fi

echo "✅ Python: $(python3 --version)"
echo "✅ Node: $(node --version)"

# ── 检查 .env ──────────────────────────────
if [ ! -f "$APP_DIR/.env" ]; then
    echo ""
    echo "⚠️  未找到 .env 配置文件"
    echo "请复制 .env.example 并填入真实凭证:"
    echo "  cp $APP_DIR/.env.example $APP_DIR/.env"
    echo "  vim $APP_DIR/.env"
    exit 1
fi

# ── 构建前端 ────────────────────────────────
echo ""
echo "📦 构建前端..."
cd "$APP_DIR/frontend"
npm install
npm run build

# ── 安装后端依赖 ───────────────────────────
echo ""
echo "🐍 安装后端依赖..."
cd "$APP_DIR/backend"
pip3 install -r requirements.txt --user

# ── 启动服务 ────────────────────────────────
echo ""
echo "🌐 启动服务..."
echo ""
echo "  访问地址: http://$(hostname -I | awk '{print $1}'):8080"
echo ""
python3 -m uvicorn main:app --host 0.0.0.0 --port 8080
