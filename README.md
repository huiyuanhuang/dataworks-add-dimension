# DataWorks 加维度 Web 工具

基于 `dataworks-add-dimension` skill 的可视化 Web 工具。

## 技术栈

- **前端**: Vue 3 + Vite + Element Plus
- **后端**: Python FastAPI + uvicorn

## 启动

```bash
cd /Users/huanghuiyuan/Documents/Playground/dataworks-add-dimension
./start.sh
```

或分别启动：

```bash
# Backend
cd backend
uvicorn main:app --reload --port 8080

# Frontend
cd frontend
npm run dev
```

## 访问

- 前端: http://localhost:5173
- 后端 API: http://localhost:8080
- API 文档: http://localhost:8080/docs

## 5 步流程

1. **配置**: 选择项目空间、输入表名和维度
2. **分析**: 展示上下游分析结果，处理上游缺失问题
3. **修改**: SQL diff 预览、修改确认
4. **执行**: 汇总确认清单（alter table / 回刷 / BI 同步）
5. **完成**: 结果展示
