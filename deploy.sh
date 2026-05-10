#!/bin/bash
# DataWorks 加维度工具 — 一键部署脚本（无 Docker 版）

set -e

# ── 配置 ──────────────────────────────────────
APP_DIR="${1:-/opt/dataworks-add-dimension}"
APP_USER="${2:-$(whoami)}"
PORT="${3:-8080}"

# ── 颜色 ──────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}🚀 DataWorks 加维度工具 一键部署${NC}"
echo ""

# ── 检查依赖 ──────────────────────────────────
echo -e "${YELLOW}📋 检查依赖...${NC}"

if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ 请先安装 Python 3.11+${NC}"
    exit 1
fi

if ! command -v node &> /dev/null; then
    echo -e "${RED}❌ 请先安装 Node.js 20+${NC}"
    exit 1
fi

if ! command -v npm &> /dev/null; then
    echo -e "${RED}❌ 请先安装 npm${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Python: $(python3 --version)${NC}"
echo -e "${GREEN}✅ Node: $(node --version)${NC}"

# ── 创建目录 ──────────────────────────────────
echo -e "${YELLOW}📁 创建应用目录...${NC}"
mkdir -p "$APP_DIR"
cd "$APP_DIR"

# ── 复制代码 ──────────────────────────────────
echo -e "${YELLOW}📦 复制代码到 $APP_DIR...${NC}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
rsync -av --exclude='node_modules' --exclude='__pycache__' --exclude='.git' "$SCRIPT_DIR/" "$APP_DIR/"

# ── 安装后端依赖 ─────────────────────────────
echo -e "${YELLOW}🐍 安装后端依赖...${NC}"
cd "$APP_DIR/backend"
pip3 install -r requirements.txt --user

# ── 构建前端 ─────────────────────────────────
echo -e "${YELLOW}🔨 构建前端...${NC}"
cd "$APP_DIR/frontend"
npm install
npm run build

# ── 配置环境变量 ─────────────────────────────
echo -e "${YELLOW}🔑 配置环境变量...${NC}"
if [ ! -f "$APP_DIR/.env" ]; then
    cat > "$APP_DIR/.env" << 'EOF'
# DataWorks 配置
DATAWORK_ACCESS_ID=
DATAWORK_ACCESS_KEY=
DATAWORK_REGION_ID=ap-southeast-1
EOF
    echo -e "${YELLOW}⚠️  请编辑 $APP_DIR/.env 填入你的 DataWorks 凭证${NC}"
fi

# ── 创建 systemd 服务 ────────────────────────
echo -e "${YELLOW}⚙️  创建 systemd 服务...${NC}"

sudo bash -c "cat > /etc/systemd/system/dataworks-add-dimension.service << EOF
[Unit]
Description=DataWorks Add Dimension Tool
After=network.target

[Service]
Type=simple
User=$APP_USER
WorkingDirectory=$APP_DIR/backend
Environment=PATH=$(which python3 | xargs dirname)
EnvironmentFile=$APP_DIR/.env
ExecStart=$(which python3) -m uvicorn main:app --host 0.0.0.0 --port $PORT
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF"

sudo systemctl daemon-reload
sudo systemctl enable dataworks-add-dimension

echo ""
echo -e "${GREEN}✅ 部署完成！${NC}"
echo ""
echo -e "${GREEN}📍 应用目录: $APP_DIR${NC}"
echo -e "${GREEN}📍 服务端口: $PORT${NC}"
echo -e "${GREEN}📍 服务用户: $APP_USER${NC}"
echo ""
echo -e "${YELLOW}🚀 启动命令:${NC}"
echo "   sudo systemctl start dataworks-add-dimension"
echo ""
echo -e "${YELLOW}📊 查看日志:${NC}"
echo "   sudo journalctl -u dataworks-add-dimension -f"
echo ""
echo -e "${YELLOW}🔑 重要：编辑配置文件${NC}"
echo "   nano $APP_DIR/.env"
echo ""
