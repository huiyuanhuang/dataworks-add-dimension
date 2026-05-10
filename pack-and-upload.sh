#!/bin/bash
# 本地打包并上传到服务器
# 用法: ./pack-and-upload.sh [服务器地址]

SERVER="${1:-webserver@sg-reco-test-001}"
SERVER_DIR="/home/webserver/app"
PROJECT_DIR="/Users/huanghuiyuan/myproject/dataworks-add-dimension"

echo "🚀 打包并上传到 $SERVER"

# 1. 进入项目目录
cd "$PROJECT_DIR"

# 2. 确保 dist 已构建
if [ ! -d "frontend/dist" ]; then
    echo "📦 dist/ 不存在，先构建前端..."
    cd frontend
    npm install
    npm run build
    cd ..
fi

echo "✅ dist/ 已就绪"

# 3. 创建上传包
echo "📦 创建上传包..."
tar czf /tmp/dataworks-add-dimension.tar.gz \
    --exclude='frontend/node_modules' \
    --exclude='backend/__pycache__' \
    --exclude='.git' \
    --exclude='.DS_Store' \
    --exclude='*.pyc' \
    backend/ frontend/dist/ .env.example README.md start.sh run.sh

# 4. 上传到服务器
echo "☁️  上传到服务器..."
scp /tmp/dataworks-add-dimension.tar.gz $SERVER:$SERVER_DIR/

# 5. 在服务器上解压
echo "📂 在服务器上解压..."
ssh $SERVER "
    cd $SERVER_DIR
    if [ -d 'dataworks-add-dimension' ]; then
        echo '备份旧版本...'
        mv dataworks-add-dimension dataworks-add-dimension-backup-\$(date +%Y%m%d-%H%M%S)
    fi
    tar xzf dataworks-add-dimension.tar.gz
    rm dataworks-add-dimension.tar.gz
    echo '✅ 解压完成，目录: $SERVER_DIR/dataworks-add-dimension'
"

echo ""
echo "✅ 上传完成！"
echo ""
echo "下一步：登录服务器并配置 .env，然后启动服务"
echo "  ssh $SERVER"
echo "  cd $SERVER_DIR/dataworks-add-dimension"
echo "  cp .env.example .env && vim .env"
echo "  cd backend && python3 -m uvicorn main:app --host 0.0.0.0 --port 8080"
