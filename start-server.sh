#!/bin/bash
# DataWorks 加维度工具 — 服务器启动脚本
# 用法: ./start-server.sh [port]

set -e

APP_DIR="$(cd "$(dirname "$0")" && pwd)"

# ── Load .env file ──────────────────────────────
if [ -f "$APP_DIR/.env" ]; then
    echo "📋 加载环境变量: $APP_DIR/.env"
    set -a
    source "$APP_DIR/.env"
    set +a
fi
PORT="${1:-8080}"

echo "🚀 DataWorks 加维度工具 — 服务器启动"
echo ""

# ── 检查 Python ──────────────────────────────
echo "📋 检查 Python 环境..."

# 尝试找到 Python 3.11+
PYTHON_CMD=""
for cmd in python3.11 python3.10 python3.9 python3.8 python3; do
    if command -v $cmd &> /dev/null; then
        version=$($cmd -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || echo "0.0")
        major=$(echo $version | cut -d. -f1)
        minor=$(echo $version | cut -d. -f2)
        if [ "$major" -ge 3 ] && [ "$minor" -ge 8 ]; then
            PYTHON_CMD=$cmd
            echo "✅ 找到 Python $version: $cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    echo "❌ 未找到 Python 3.8+，当前版本:"
    python3 --version 2>/dev/null || echo "未找到 python3"
    echo ""
    echo "请安装 Python 3.8+，推荐方式："
    echo ""
    echo "方式1: conda（推荐）"
    echo "  wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O /tmp/miniconda.sh"
    echo "  bash /tmp/miniconda.sh -b -p ~/miniconda3"
    echo "  ~/miniconda3/bin/conda init bash && source ~/.bashrc"
    echo "  conda create -n dataworks python=3.11 -y"
    echo "  conda activate dataworks"
    echo ""
    echo "方式2: pyenv"
    echo "  curl https://pyenv.run | bash"
    echo "  pyenv install 3.11.0"
    echo "  pyenv global 3.11.0"
    exit 1
fi

# ── 检查 .env ──────────────────────────────
echo ""
cd "$APP_DIR"
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        echo "⚠️  首次运行，请配置 .env 文件"
        echo ""
        echo "请编辑 .env 文件，填入你的 DataWorks 凭证:"
        echo "  cp .env.example .env"
        echo "  vim .env"
        echo ""
        echo ".env 文件需要包含:"
        echo "  DATAWORK_ACCESS_ID=你的AccessKey ID"
        echo "  DATAWORK_ACCESS_KEY=你的AccessKey Secret"
        echo "  DATAWORK_REGION_ID=ap-southeast-1"
        exit 1
    else
        echo "❌ 未找到 .env 和 .env.example 文件"
        exit 1
    fi
fi

# ── 检查依赖 ──────────────────────────────
echo ""
echo "🐍 检查 Python 依赖..."
cd "$APP_DIR/backend"

# 检查 fastapi 是否已安装
if ! $PYTHON_CMD -c "import fastapi" 2>/dev/null; then
    echo "📦 安装依赖..."
    $PYTHON_CMD -m pip install -r requirements.txt --user
fi

echo "✅ 依赖已就绪"

# ── 获取 IP ────────────────────────────────
LOCAL_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "$(hostname)")

# ── 启动服务 ────────────────────────────────
echo ""
echo "🌐 启动服务..."
echo ""
echo "  访问地址:"
echo "    本机:   http://localhost:$PORT"
echo "    局域网: http://$LOCAL_IP:$PORT"
echo "    API文档: http://$LOCAL_IP:$PORT/docs"
echo ""
$PYTHON_CMD -m uvicorn main:app --host 0.0.0.0 --port "$PORT"
