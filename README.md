# MindDock

MindDock is an open-source personal knowledge assistant backend for a graduation project.  
The current repository focuses on a minimal but demonstrable RAG workflow:

- build a local knowledge base
- search within that knowledge base
- answer questions with citations
- summarize a topic with citations
- maintain the knowledge base through full rebuilds or incremental updates

## Current Scope

Implemented now:

- FastAPI backend with `/`, `/health`, `/search`, `/chat`, and `/summarize`
- Local document ingestion for `.md` and `.txt`
- Chroma-backed persistence
- Minimal metadata filters: `source`, `section`
- Grounded answers and summaries with traceable citations
- Incremental knowledge-base maintenance for file create / modify / delete

Not implemented yet:

- PDF or URL ingestion
- profile-driven orchestration
- structured outputs
- frontend UI
- CI/CD

## Quick Start

### 1. Create and activate a virtual environment

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

macOS / Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

Using `uv`:

```bash
uv sync
```

Using `pip`:

```bash
pip install -U pip
pip install fastapi uvicorn[standard] pydantic-settings chromadb sentence-transformers httpx watchdog
pip install -e ".[dev]"
```

### 3. Prepare demo data

Put one or more `.md` or `.txt` files under `knowledge_base/`.

Example:

```text
knowledge_base/
  example.md
```

### 4. Build the knowledge base

```bash
python -m app.rag.ingest --rebuild
```

Expected output:

```text
Loaded N documents
Created M chunks
Stored to Chroma
```

### 5. Start the API

```bash
uvicorn app.main:app --reload
```

Default address:

```text
http://127.0.0.1:8000
```

## Health Check

```bash
curl http://127.0.0.1:8000/health
```

Expected response:

```json
{"status":"ok","service":"MindDock","version":"0.1.0"}
```

## API Examples

### `/search`

Purpose:
- retrieve the most relevant chunks from the knowledge base

Example request:

```bash
curl -X POST http://127.0.0.1:8000/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "storage design",
    "top_k": 3,
    "filters": {
      "source": "notes.md",
      "section": "Storage"
    }
  }'
```

Response shape:

```json
{
  "query": "storage design",
  "top_k": 3,
  "hits": [
    {
      "text": "MindDock stores chunks in local Chroma.",
      "doc_id": "...",
      "chunk_id": "...:0",
      "source": "notes.md",
      "distance": 0.1
    }
  ]
}
```

What to look at in a demo:
- `hits` gets smaller when filters are added
- `source` shows the matched file scope

### `/chat`

Purpose:
- answer a question using retrieved evidence only

Example request:

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "query": "where is the data stored",
    "top_k": 3,
    "filters": {
      "source": "notes.md",
      "section": "Storage"
    }
  }'
```

Response shape:

```json
{
  "answer": "According to the retrieved evidence ...",
  "citations": [
    {
      "doc_id": "...",
      "chunk_id": "...:0",
      "source": "notes.md",
      "snippet": "MindDock stores chunks in local Chroma.",
      "title": "notes",
      "section": "Storage",
      "location": "Storage",
      "ref": "notes > Storage"
    }
  ],
  "retrieved_count": 1
}
```

What to look at in a demo:
- `answer` should stay grounded and conservative
- `citations` should show where the answer came from
- `ref`, `section`, and `location` are the easiest fields to explain during defense

### `/summarize`

Purpose:
- summarize a topic from multiple retrieved chunks

Input supports either `topic` or `query`.

Example request:

```bash
curl -X POST http://127.0.0.1:8000/summarize \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "storage design",
    "top_k": 5,
    "filters": {
      "source": "notes.md"
    }
  }'
```

Response shape:

```json
{
  "summary": "Around storage design, the current evidence shows ...",
  "citations": [
    {
      "doc_id": "...",
      "chunk_id": "...:0",
      "source": "notes.md",
      "snippet": "MindDock stores chunks in local Chroma.",
      "title": "notes",
      "section": "Storage",
      "location": "Storage",
      "ref": "notes > Storage"
    }
  ],
  "retrieved_count": 1
}
```

What to look at in a demo:
- `summary` is synthesis-oriented instead of question-answer style
- the same citation structure is reused from `/chat`

## Filters

The current minimal filters are:

- `source`
- `section`

These filters work the same way for:

- `/search`
- `/chat`
- `/summarize`

Notes:

- filters are optional
- if omitted, behavior stays backward compatible
- filtering is exact-match style, not fuzzy search or boolean logic

## Knowledge Base Maintenance

### Full rebuild

Use this when:

- setting up the repository for the first time
- changing many files at once
- wanting to refresh metadata consistently

```bash
python -m app.rag.ingest --rebuild
```

### Incremental watch mode

Use this when:

- manually demonstrating file create / modify / delete updates
- showing engineering support for long-running maintenance

```bash
set WATCH_ENABLED=true
python -m app.rag.watcher
```

What it is best for:

- manual demo
- showing the architecture boundary between file events and incremental updates

What it is not best for:

- strict automated end-to-end timing tests across different OS environments

See also:

- `docs/ARCHITECTURE_OVERVIEW.md`
- `docs/INCREMENTAL_DEMO.md`
- `docs/DEMO_FLOW.md`

## Recommended Defense Demo Order

1. Run full ingest
2. Show `/search`
3. Show `/chat`
4. Show `/summarize`
5. Show incremental update with watcher

This order works well because it moves from infrastructure to user-facing capability.

## Environment Notes

### Re-ingest before demo?

Recommended: yes.

Why:
- citation metadata and filters depend on current stored chunk metadata
- rebuilding once before a defense reduces "why didn't this hit update?" risk

### DummyEmbedding vs real embedding

If `sentence-transformers` is unavailable, the system falls back to `DummyEmbedding`.

Meaning:
- the pipeline still works
- the demo remains runnable
- retrieval quality is weaker and less semantically accurate

For a stronger defense demo, install `sentence-transformers` successfully before presenting.

### API key vs no API key

Without `LLM_API_KEY`:
- `/chat` and `/summarize` still work via `MockLLM`
- output remains readable and grounded, but simpler

With `LLM_API_KEY`:
- the OpenAI-compatible provider is used
- output quality can improve, but the demo depends on network and provider availability

For a stable on-site demo, the no-key path is safer.

## Tests

Run the full test suite:

```bash
python -m pytest
```

If you changed incremental maintenance:

```bash
python -m pytest tests/unit/test_incremental_ingest.py tests/unit/test_watcher.py
```

## Documentation Map

- `docs/STATUS.md`: current implementation status
- `docs/ROADMAP.md`: planned milestones
- `docs/ARCHITECTURE_OVERVIEW.md`: concise code-aligned architecture map
- `docs/TEST_PLAN.md`: test scope and validation guidance
- `docs/INCREMENTAL_DEMO.md`: focused incremental maintenance demo
- `docs/DEMO_FLOW.md`: end-to-end defense demo flow
- `docs/CHANGELOG.md`: active modification log

## Current Limitations

- only `.md` and `.txt` ingestion is supported
- filters support only `source` and `section`
- watcher is better for manual demo than for deterministic automated testing
- summary is a minimal grounded summarization, not a full Map-Reduce pipeline
- retrieval quality depends strongly on embedding availability

## Open Source Notes

- License: `MIT`
- Update `docs/CHANGELOG.md` before every push
- Historical stage reports in `docs/reports/` are preserved as records and should not be rewritten during routine maintenance

