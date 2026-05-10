#!/bin/bash
# 最简单运行方式（开发/测试用）
# 用法: ./run.sh

cd "$(dirname "$0")"

echo "🚀 启动 DataWorks 加维度工具..."

# 1. 构建前端
echo "📦 构建前端..."
cd frontend
npm install
npm run build
cd ..

# 2. 安装后端依赖
echo "🐍 检查后端依赖..."
cd backend
pip3 install -r requirements.txt --user

# 3. 启动服务
echo "🌐 启动服务..."
python3 -m uvicorn main:app --host 0.0.0.0 --port 8080
