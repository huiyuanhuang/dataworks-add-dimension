# DataWorks 加维度 Web 工具实现计划

> **For agentic workers:** Use superpowers:executing-plans or manual execution. Steps use checkbox syntax.

**Goal:** 构建一个可视化 Web 工具，将 dataworks-add-dimension skill 的完整流程转化为 5 步骤交互界面。

**Architecture:** FastAPI 后端提供 REST API，复用现有 Python 脚本；Vue 3 前端提供步骤条向导式 UI；前后端通过 CORS 通信，本机部署。

**Tech Stack:** Vue 3 + Vite + Element Plus (frontend) | Python FastAPI + uvicorn (backend)

---

## Task 1: 后端骨架搭建

**Files:**
- Create: `backend/main.py`
- Create: `backend/requirements.txt`
- Create: `backend/routers/__init__.py`
- Create: `backend/routers/projects.py`
- Create: `backend/routers/analysis.py`
- Create: `backend/routers/execution.py`
- Create: `backend/services/dataworks_service.py`

- [ ] **Step 1: 创建 requirements.txt**
```
fastapi>=0.100.0
uvicorn>=0.23.0
python-multipart>=0.0.6
pydantic>=2.0.0
```

- [ ] **Step 2: 创建 main.py 启动 FastAPI**
```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import projects, analysis, execution

app = FastAPI(title="DataWorks Add Dimension API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(projects.router, prefix="/api/projects")
app.include_router(analysis.router, prefix="/api/analysis")
app.include_router(execution.router, prefix="/api/execution")
```

- [ ] **Step 3: 创建 projects router**
返回 mock 项目列表（实际调用 query_dataworks_task.py --scan-projects）

- [ ] **Step 4: 验证后端启动**
```bash
uvicorn main:app --reload --port 8000
```

## Task 2: 前端骨架搭建

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/vite.config.js`
- Create: `frontend/index.html`
- Create: `frontend/src/main.js`
- Create: `frontend/src/App.vue`
- Create: `frontend/src/api/index.js`

- [ ] **Step 1: 初始化 Vue 3 项目**
```bash
cd frontend && npm create vue@latest . -- --template vanilla
# 然后安装 element-plus
npm install element-plus vue@3 vue-router@4 pinia axios
```

- [ ] **Step 2: 配置 vite.config.js**
```javascript
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
export default defineConfig({ plugins: [vue()], server: { port: 5173, proxy: { '/api': 'http://localhost:8000' } } })
```

- [ ] **Step 3: 创建 main.js**
```javascript
import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import App from './App.vue'
createApp(App).use(ElementPlus).mount('#app')
```

- [ ] **Step 4: 创建 App.vue（步骤条容器）**
包含 el-steps（5步）+ router-view

- [ ] **Step 5: 验证前端启动**
```bash
npm run dev
```

## Task 3: Step 1 - 配置页面

**Files:**
- Create: `frontend/src/components/StepConfig.vue`
- Modify: `backend/routers/projects.py`

- [ ] **Step 1: 后端 /api/projects/list 返回项目列表**
调用 query_dataworks_task.py --scan-projects 或直接返回 mock

- [ ] **Step 2: 前端 StepConfig 组件**
包含：项目下拉选择、表名输入、维度名输入、中文名输入

- [ ] **Step 3: 添加表单验证**
必填校验 + 开始分析按钮

## Task 4: Step 2 - 分析页面

**Files:**
- Create: `frontend/src/components/StepAnalyze.vue`
- Modify: `backend/routers/analysis.py`
- Create: `backend/services/sql_analyzer.py`

- [ ] **Step 1: 后端 /api/analysis/analyze 接口**
接收 project + table + dimension，返回：
- 原始 SQL
- 上游表列表及字段存在状态
- 下游节点列表
- 维度展开方式识别

- [ ] **Step 2: 前端分析结果展示**
上游表格：表名 | 字段存在 | 来源推断
下游复选框：节点列表 + 勾选
问题弹窗：如果上游缺失，展示选项

## Task 5: Step 3 - 修改页面

**Files:**
- Create: `frontend/src/components/StepModify.vue`
- Modify: `backend/routers/analysis.py`

- [ ] **Step 1: 后端 /api/analysis/modify 接口**
接收确认参数，返回：
- 修改后 SQL
- diff 信息（新增行标记）
- alter table SQL

- [ ] **Step 2: 前端 diff 展示**
左右分栏：原始 SQL（只读）+ 修改 SQL（可编辑）
高亮新增行

## Task 6: Step 4 - 执行页面

**Files:**
- Create: `frontend/src/components/StepExecute.vue`
- Modify: `backend/routers/execution.py`

- [ ] **Step 1: 汇总确认清单**
Checklist：SQL diff 确认、alter table（可选）、历史回刷（可选）、提交 ODPS（可选）、BI 同步（可选）

- [ ] **Step 2: 后端执行接口**
/api/execution/save-draft
/api/execution/alter-table
/api/execution/backfill

## Task 7: Step 5 - 完成页面

**Files:**
- Create: `frontend/src/components/StepComplete.vue`

- [ ] **Step 1: 结果展示**
节点信息、执行状态、BI 同步结果

- [ ] **Step 2: 重新开始按钮**

## Task 8: 集成与部署

- [ ] **Step 1: 前后端联调**
- [ ] **Step 2: 启动脚本**
创建 start.sh 同时启动前后端
- [ ] **Step 3: README 文档**
