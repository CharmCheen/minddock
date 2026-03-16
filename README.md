# MindDock

Open-source personal knowledge assistant backend powered by RAG and agent workflows.

## Overview

Current version provides a runnable FastAPI service with base health-check endpoints.
RAG, vector store, and LLM features are included incrementally in the project structure.

## Current Scope

- FastAPI backend with `/`, `/health`, `/search`, and `/chat`
- Local knowledge ingestion for `.md` and `.txt`
- Chroma-backed persistence
- Minimal grounded response flow with citations
- Domain and port contracts for future extension

## Project Docs

- `docs/STATUS.md`: current implementation status
- `docs/ROADMAP.md`: planned milestones
- `docs/TEST_PLAN.md`: test scope and local validation
- `docs/CHANGELOG.md`: active modification log, must be updated before every push
- `CONTRIBUTING.md`: contribution rules and push workflow

## 1. Create and Activate a Virtual Environment

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

## 2. Install Dependencies

### Using pip
```bash
pip install -U pip
pip install fastapi uvicorn[standard] pydantic-settings
```

### Or using uv
```bash
uv sync
```

### Development dependencies
```bash
pip install -e ".[dev]"
```

## 3. Start the Service

```bash
uvicorn app.main:app --reload
```

The service listens on `http://127.0.0.1:8000` by default.

## 4. Health Check

```bash
curl http://127.0.0.1:8000/health
```

Expected response:

```json
{"status":"ok","service":"MindDock","version":"0.1.0"}
```

## 5. Optional Environment Variables

- `APP_NAME`: service name, default `MindDock`
- `APP_VERSION`: service version, default `0.1.0`
- `LOG_LEVEL`: log level, default `INFO`

## Document Ingestion

Run the ingestion CLI:

```bash
python -m app.rag.ingest --rebuild
```

Place knowledge files under `knowledge_base/`.
Only `.md` and `.txt` files are processed at this stage.

The pipeline will:

- Load documents from `knowledge_base`
- Split content into chunks
- Generate embeddings
- Store chunks and metadata in local Chroma at `data/chroma`

Notes:

- If `sentence-transformers` model download or initialization fails, ingestion falls back to a deterministic dummy embedding
- Dummy embeddings are for local development only

## Tests

Run:

```bash
python -m pytest
```

## Open Source Notes

- License: `MIT`
- Please update `docs/CHANGELOG.md` before every push
- Historical stage reports under `docs/reports/` are preserved as records and should not be rewritten during routine maintenance
