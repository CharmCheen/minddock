# 个人知识管理助手（RAG+Agent）- 第1步最小骨架

当前版本仅提供可运行的 FastAPI 服务与健康检查接口，暂不包含 RAG/向量库/LLM 功能。

## 1. 创建虚拟环境并激活

### Windows (PowerShell)
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### macOS / Linux
```bash
python3 -m venv .venv
source .venv/bin/activate
```

## 2. 安装依赖

### 使用 pip
```bash
pip install -U pip
pip install fastapi uvicorn[standard] pydantic-settings
```

### 或使用 uv（可选）
```bash
uv sync
```

## 3. 启动服务

```bash
uvicorn app.main:app --reload
```

服务默认监听 `http://127.0.0.1:8000`。

## 4. 健康检查

```bash
curl http://127.0.0.1:8000/health
```

期望返回：

```json
{"status":"ok","service":"pka","version":"0.1.0"}
```

## 5. 可选环境变量

- `APP_NAME`：服务名称（默认 `pka`）
- `APP_VERSION`：服务版本（默认 `0.1.0`）
- `LOG_LEVEL`：日志级别（默认 `INFO`）

## STEP 2 - Document ingestion

Run ingestion CLI:

```bash
python -m app.rag.ingest --rebuild
```

Place your knowledge files under `knowledge_base/`.
Only `.md` and `.txt` files are processed in this step.

The pipeline will:
- Load documents from `knowledge_base`
- Split content into chunks
- Generate embeddings
- Store chunks and metadata into local Chroma at `data/chroma`

Note:
- If `sentence-transformers` model download/init fails, ingestion falls back to a deterministic dummy embedding.
- Dummy embedding is for local development only.
