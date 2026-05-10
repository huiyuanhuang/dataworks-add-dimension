# 部署指南

## 方式一：Docker 部署（推荐）

### 1. 构建镜像

```bash
cd /Users/huanghuiyuan/Documents/Playground/dataworks-add-dimension

# 确保环境变量文件存在
touch .env

# 构建镜像
docker build -t dataworks-add-dimension:latest .
```

### 2. 运行容器

```bash
# 方式 A：直接运行
docker run -d \
  --name dataworks-add-dimension \
  -p 8080:8080 \
  -e DATAWORK_ACCESS_ID=your_access_id \
  -e DATAWORK_ACCESS_KEY=your_access_key \
  -e DATAWORK_REGION_ID=ap-southeast-1 \
  --restart unless-stopped \
  dataworks-add-dimension:latest

# 方式 B：使用 docker-compose（推荐）
docker-compose up -d
```

### 3. 查看日志

```bash
docker logs -f dataworks-add-dimension
```

---

## 方式二：服务器直接部署

### 前置条件

- Python 3.11+
- Node.js 20+
- 环境变量已配置

### 1. 克隆代码到服务器

```bash
git clone <your-repo-url> /opt/dataworks-add-dimension
cd /opt/dataworks-add-dimension
```

### 2. 安装后端依赖

```bash
cd backend
pip install -r requirements.txt
```

### 3. 构建前端

```bash
cd ../frontend
npm install
npm run build
```

### 4. 配置环境变量

```bash
# 编辑 /etc/systemd/system/dataworks-add-dimension.service
# 或创建 .env 文件
echo "DATAWORK_ACCESS_ID=your_access_id" > /opt/dataworks-add-dimension/.env
echo "DATAWORK_ACCESS_KEY=your_access_key" >> /opt/dataworks-add-dimension/.env
```

### 5. 使用 systemd 管理（推荐）

```bash
sudo cat > /etc/systemd/system/dataworks-add-dimension.service << 'SYSTEMD'
[Unit]
Description=DataWorks Add Dimension Tool
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/dataworks-add-dimension/backend
Environment="PATH=/usr/local/bin"
EnvironmentFile=/opt/dataworks-add-dimension/.env
ExecStart=/usr/local/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8080
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SYSTEMD

sudo systemctl daemon-reload
sudo systemctl enable dataworks-add-dimension
sudo systemctl start dataworks-add-dimension
```

---

## 方式三：Nginx 反向代理（生产环境）

### 1. 配置 Nginx

```bash
sudo cat > /etc/nginx/sites-available/dataworks-add-dimension << 'NGINX'
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
NGINX

sudo ln -s /etc/nginx/sites-available/dataworks-add-dimension /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 2. 配置 HTTPS（Let's Encrypt）

```bash
sudo certbot --nginx -d your-domain.com
```

---

## 环境变量说明

| 变量名 | 必填 | 说明 |
|--------|------|------|
| `DATAWORK_ACCESS_ID` | 是 | DataWorks Access ID |
| `DATAWORK_ACCESS_KEY` | 是 | DataWorks Access Key |
| `DATAWORK_REGION_ID` | 否 | 区域，默认 `ap-southeast-1` |
| `ODPS_ENDPOINT` | 否 | ODPS 端点 |
| `DATAWORK_REGION_ID` | 否 | 阿里云区域 |

---

## 健康检查

```bash
# 检查服务是否正常运行
curl http://localhost:8080/api/health

# 预期返回
# {"status":"ok"}
```

---

## 更新部署

### Docker 方式

```bash
cd /opt/dataworks-add-dimension
git pull
docker build -t dataworks-add-dimension:latest .
docker-compose down
docker-compose up -d
```

### systemd 方式

```bash
cd /opt/dataworks-add-dimension
git pull
cd frontend && npm run build
cd ../backend
sudo systemctl restart dataworks-add-dimension
```
