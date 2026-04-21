# MindDock — 快速启动指南

> 面向本地私有文档的 AI 知识管理助手后端。提供 RAG 检索、引用溯源、多任务对比/摘要等能力。

---

## 前提条件

* Python 3.11+
* Node.js 18+ (for frontend)
* pip 或 uv

---

## 方式一：本地开发启动（推荐用于开发调试）

### 1. 安装后端依赖

```bash
# 使用 uv（推荐，fast）
uv sync

# 或使用 pip
pip install -e .
```

### 2. 配置环境变量

```bash
# 复制示例环境文件
cp .env.minimax.local .env

# 编辑 .env 填入你的 LLM API key
# LLM_API_KEY=sk-...
# LLM_BASE_URL=https://api.minimaxi.com/v1  # 或 https://api.openai.com/v1
# LLM_MODEL=MiniMax-M2.7  # 或 gpt-4o-mini
```

### 3. 启动后端服务

```bash
uvicorn app.main:app --reload --port 8000
```

服务地址: http://127.0.0.1:8000

### 4. 入库示例文档（首次运行）

```bash
# 用内置 CLI 入库 knowledge_base/ 目录下的所有文档
python -m app.rag.ingest

# 如果想重建（清空旧数据后重新入库）
python -m app.rag.ingest --rebuild
```

### 5. 启动前端（独立运行）

```bash
cd frontend
npm install
npm run dev
```

前端地址: http://localhost:5173

---

## 方式二：Docker Compose 启动（推荐用于演示/快速复现）

### 1. 配置环境变量

```bash
cp .env.minimax.local .env
# 编辑 .env 填入你的 LLM API key
```

### 2. 构建并启动

```bash
docker-compose up --build
```

### 3. 入库示例文档（容器内执行）

```bash
# 进入运行中的容器
docker exec -it minddock-backend bash

# 执行入库
python -m app.rag.ingest
```

### 4. 验证

```bash
# 健康检查
curl http://localhost:8000/health

# 列出已入库文档
curl http://localhost:8000/sources

# 发起一个 chat 问答测试
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "这是什么系统？", "top_k": 3}'
```

---

## 核心 API 快速验证

### 健康检查

```bash
curl http://127.0.0.1:8000/health
# {"status":"ok","service":"MindDock","version":"0.1.0"}
```

### 文档入库

```bash
curl -X POST http://127.0.0.1:8000/ingest \
  -H "Content-Type: application/json" \
  -d '{"rebuild": false, "urls": []}'
```

### 检索问答

```bash
# chat（带引用）
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "你的知识库包含哪些内容？", "top_k": 3}'

# summarize（摘要）
curl -X POST http://127.0.0.1:8000/summarize \
  -H "Content-Type: application/json" \
  -d '{"topic": "RAG", "top_k": 5, "mode": "basic"}'

# compare（对比分析）
curl -X POST http://127.0.0.1:8000/compare \
  -H "Content-Type: application/json" \
  -d '{"question": "比较 RAG 和 Fine-tuning 两种方法", "top_k": 6}'

# search（纯检索）
curl -X POST http://127.0.0.1:8000/search \
  -H "Content-Type: application/json" \
  -d '{"query": "知识管理", "top_k": 5}'
```

---

## 目录结构说明

```
knowledge_base/    # 源文档目录，放入 .md/.txt/.pdf 文件
data/chroma/      # Chroma 向量数据库持久化目录
logs/             # 运行日志目录
```

---

## 常见问题

### Q: 启动报 "langchain / langgraph not installed"
A: `uv sync` 会自动安装所有依赖。如使用 pip，直接 `pip install -e .`

### Q: 没有 LLM API key 也能跑吗？
A: 可以。后端内置 MockLLM fallback，会返回预设答案。但无法展示真实生成效果。

### Q: 入库后检索结果为空
A: 检查 knowledge_base/ 下是否有支持的文档（.md / .txt / .pdf）。也可以先调用 `/sources` 确认已有文档入库。

### Q: 前端无法连接后端
A: 确认后端在 8000 端口运行。前端默认连接 `http://127.0.0.1:8000`，如需修改，配置 `frontend/.env` 中的 `VITE_API_BASE_URL`。
