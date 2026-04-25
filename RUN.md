# MindDock 运行说明

本文档给出最稳的本地运行路径，用于毕业设计演示和答辩前自检。

## 1. 环境要求

- Python 3.11
- Conda 环境名：`minddock`
- Node.js 18+，npm
- 可选：LLM API key。未配置时系统会使用 mock fallback，流程可跑通，但生成质量不代表真实模型效果。
- Chroma 数据目录：`data/chroma/`
- 演示文档目录：`knowledge_base/`

## 2. 创建后端环境

首次运行：

```powershell
conda env create -f environment.yml
conda activate minddock
```

如果环境已存在：

```powershell
conda activate minddock
```

安装项目依赖：

```powershell
pip install -e ".[dev]"
```

## 3. LLM 配置

如果需要真实模型生成，请准备 `.env` 或通过前端 runtime settings 配置模型。

可参考：

```powershell
copy .env.minimax.local .env
```

然后填入自己的 API key。不要把真实 key 提交到 Git。

没有 API key 时，系统会走 mock fallback，适合验证 API、检索、citation、source 展示链路。

## 4. 构建或复用索引

仓库中已有 `knowledge_base/` 示例文档，也可能已有 `data/chroma/` 索引。

如果需要重新入库：

```powershell
conda run --no-capture-output -n minddock python -m app.demo ingest
```

如果只想追加 URL：

```powershell
conda run --no-capture-output -n minddock python -m app.demo ingest --no-rebuild --url https://example.com
```

## 5. 启动后端

推荐演示命令：

```powershell
conda activate minddock
python -m app.demo serve
```

默认地址：

```text
http://127.0.0.1:8000
```

也可以直接使用 uvicorn：

```powershell
uvicorn app.main:app --reload --port 8000
```

健康检查：

```powershell
conda run --no-capture-output -n minddock python -m app.demo health --via-api
```

或浏览器打开：

```text
http://127.0.0.1:8000/health
http://127.0.0.1:8000/docs
```

## 6. 启动前端

```powershell
cd frontend
npm install
npm run dev
```

Vite 默认地址：

```text
http://localhost:5173
```

前端构建检查：

```powershell
cd frontend
npm run build
```

## 7. Demo CLI 常用命令

列出已索引 sources：

```powershell
conda run --no-capture-output -n minddock python -m app.demo sources
```

查看某个 source 的 chunks：

```powershell
conda run --no-capture-output -n minddock python -m app.demo source-chunks --source rag_pipeline.md --limit 5
```

检索：

```powershell
conda run --no-capture-output -n minddock python -m app.demo search --query "Milvus system design" --top-k 4
```

问答：

```powershell
conda run --no-capture-output -n minddock python -m app.demo chat --query "What does the SYSTEM DESIGN section of the Milvus paper describe?" --top-k 4
```

摘要：

```powershell
conda run --no-capture-output -n minddock python -m app.demo summarize --topic "Milvus system design" --top-k 4
```

对比：

```powershell
conda run --no-capture-output -n minddock python -m app.demo compare --question "Compare the Milvus paper with the local RAG pipeline docs." --top-k 4
```

评测：

```powershell
conda run --no-capture-output -n minddock python -m app.demo evaluate --dataset eval/benchmark/sample_eval_set.jsonl
```

## 8. 测试命令

近期 RAG citation / retrieval 核心回归：

```powershell
conda run --no-capture-output -n minddock python -m pytest tests/unit/test_evidence_window.py tests/unit/test_retrieval_models.py tests/unit/test_pdf_citation.py tests/unit/test_citation.py tests/unit/test_schemas.py tests/unit/test_postprocess.py tests/unit/test_chat_service.py tests/unit/test_search_service.py -q
```

项目 baseline：

```powershell
conda run --no-capture-output -n minddock python scripts/run_ci_baseline.py
```

前端类型和构建：

```powershell
cd frontend
npm run build
```

## 9. 常见问题

### 未配置 API key

系统会使用 mock fallback。可以演示检索、citation、source drawer 和 API 流程，但生成文本质量不代表真实模型。

### Embedding 模型或 CUDA 问题

如果 `sentence-transformers` 或 GPU 不可用，系统可能降级或变慢。演示前建议提前运行一次 ingest/chat，确认 `data/chroma/` 可用。

### `data/chroma/` 不存在或检索为空

运行：

```powershell
conda run --no-capture-output -n minddock python -m app.demo ingest
```

然后再调用 `sources` 或 `chat`。

### 前端端口

Vite 默认是 `5173`。如果端口被占用，终端会提示新的端口。

### Windows 中文路径和编码

建议使用 PowerShell，并确保终端使用 UTF-8。仓库路径包含中文时，优先使用 `conda run --no-capture-output -n minddock ...`，避免环境和编码差异。

### `start.bat`

`start.bat` 可作为辅助启动脚本，但答辩演示建议优先使用本文档中的手动命令，便于定位问题。
