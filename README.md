# MindDock

MindDock is a personal knowledge management assistant backend built around a minimal RAG workflow. It is currently under active iterative development for a graduation project, with the main focus on private/local knowledge ingestion, retrieval, grounded answering, summarization, and incremental knowledge-base maintenance.

The repository is no longer just a static concept description: the backend MVP is already runnable, but several modules are still being refined toward the full graduation-project target.

## Development Status

MindDock is currently in the MVP stage.

What that means in practice:

- the core backend loop is already runnable end-to-end
- local knowledge can be ingested into a persistent Chroma store
- the API can return search hits, grounded answers, summaries, and citations
- incremental update support already exists for local file create / modify / delete
- the project is still being iterated, tested, and documented toward a more complete defense-ready system

For a lightweight progress snapshot that should stay in sync with every important push, see [docs/STATUS.md](docs/STATUS.md).

## What Works Now

Verified working parts of the current repository:

- FastAPI backend startup
- `GET /`
- `GET /health`
- local knowledge ingestion
- `.md`, `.txt`, and `.pdf` ingestion
- Chroma persistence under `data/chroma`
- `POST /search` in the basic case
- `POST /chat`
- `POST /summarize`
- citation return for search/chat/summarize
- watcher-based incremental update for file create / modify / delete
- no-key local demo path via fallback/mock LLM behavior

## Current Limitations

Known limitations that are still being worked on:

- rerank and compress are currently placeholder no-op hooks
- URL ingestion is not implemented yet
- multi-filter search is not fully stable against the current Chroma query behavior
- `/ingest` with `rebuild=true` can fail in long-running API mode on Windows because Chroma files may be locked
- real OpenAI-compatible remote generation exists in code, but local demos may still rely on the fallback/mock path
- retrieval quality depends heavily on whether `sentence-transformers` is available or the system falls back to `DummyEmbedding`
- CI workflow is not configured yet
- some documentation files may lag behind the latest code changes if not updated together

## Next Steps

Near-term roadmap for the next iteration cycle:

1. fix real runtime issues in filtered search and rebuild behavior
2. improve retrieval quality and demo consistency
3. add missing URL ingestion capability
4. replace rerank/compress placeholders with real implementations or a smaller but concrete first version
5. improve tests and add CI automation
6. keep README, status docs, and demo docs synchronized as features evolve
7. later extend toward richer workflow / agent-style orchestration beyond the current backend MVP

## Quick Start

### Shortest Demo Path

From the repository root:

```powershell
conda env create -f environment.yml
conda activate minddock
python -m app.demo ingest
python -m app.demo serve
```

Then verify the service:

```powershell
python -m app.demo health
```

Expected response:

```json
{"status":"ok","service":"MindDock","version":"0.1.0"}
```

### 1. Create and activate the recommended conda environment

Windows PowerShell:

```powershell
conda env create -f environment.yml
conda activate minddock
```

macOS / Linux:

```bash
conda env create -f environment.yml
conda activate minddock
```

This repository now treats `conda` + `environment.yml` as the preferred local/demo setup.

If you already have an older `.venv` workflow prepared, it can still work, but new local setup and demo rehearsal should prefer the conda path for consistency.

### 2. Install dependencies

The editable install is already included in `environment.yml`, so the simplest path is:

```powershell
conda env create -f environment.yml
conda activate minddock
```

If you create the environment manually instead, install with `pip`:

```powershell
conda create -n minddock python=3.11 -y
conda activate minddock
pip install -U pip
pip install -e ".[dev]"
```

Notes:

- if `sentence-transformers` is unavailable, the app falls back to `DummyEmbedding`
- the fallback path keeps the MVP runnable, but retrieval quality is weaker
- no `.env` file is required for the shortest local demo path

### 3. Prepare the knowledge base

The repository already ships with demo files under `knowledge_base/`, including Markdown and PDF samples.

Current supported local file types in code:

- `.md`
- `.txt`
- `.pdf`

### 4. Build the local vector store

```powershell
python -m app.demo ingest
```

Expected console output:

```text
Loaded N documents
Created M chunks
Stored to Chroma
```

### 5. Start the API

```powershell
python -m app.demo serve
```

Default address:

```text
http://127.0.0.1:8000
```

Interactive docs:

```text
http://127.0.0.1:8000/docs
```

## Demo API Flow

### Health check

```powershell
python -m app.demo health
```

### `/search`

```powershell
python -m app.demo search
```

What to look for:

- `hits` contains retrieved chunks
- each hit includes `doc_id`, `chunk_id`, `source`, `distance`
- each hit also includes a structured `citation`

### `/chat`

```powershell
python -m app.demo chat
```

What to look for:

- answer is built from retrieved evidence
- citations are returned together with the answer
- local demo can still run without a real remote API key

### `/summarize`

```powershell
python -m app.demo summarize
```

What to look for:

- summary is grounded in retrieved chunks
- citations reuse the same traceable structure as `/chat`

## Incremental Update Demo

Watcher mode is already useful for manual presentation/demo:

```powershell
python -m app.demo watch
```

Recommended live demo actions:

1. create a new `.md` file under `knowledge_base/`
2. modify the file and show updated retrieval behavior
3. delete the file and show the corresponding chunk removal

## Environment Notes

### Recommended environment for live demo

The currently recommended local/demo environment is:

- `conda`
- Python `3.11`
- environment created from `environment.yml`

This path has been used to validate the current demo command layer:

- `python -m app.demo ingest`
- `python -m app.demo serve`
- `python -m app.demo health`
- `python -m app.demo search`
- `python -m app.demo chat`
- `python -m app.demo summarize`

### Logging layout

MindDock now uses a fixed logging directory and layered log files:

- `logs/minddock.info.log`: business-level info, warnings, and errors
- `logs/minddock.debug.log`: debug-level diagnostics
- `logs/minddock.trace.log`: fine-grained trace events

The default directory comes from `Settings.log_dir` and currently resolves to `logs/`.

### DummyEmbedding vs real embedding

If `sentence-transformers` cannot load, the system falls back to `DummyEmbedding`.

That means:

- the project still runs locally
- the ingestion/search/chat/summarize loop still works
- semantic quality is weaker than with a real embedding model

### API key vs no API key

Without `LLM_API_KEY`:

- `/chat` and `/summarize` still work through the local fallback path
- this is usually the safer on-site demo mode

With `LLM_API_KEY`:

- the OpenAI-compatible provider can be used
- output quality may improve
- demo stability becomes more dependent on network/provider conditions

## Tests

Run the full test suite:

```powershell
python -m pytest
```

If incremental maintenance changed:

```powershell
python -m pytest tests/unit/test_incremental_ingest.py tests/unit/test_watcher.py
```

## Documentation Map

- [docs/STATUS.md](docs/STATUS.md): current stage, completed items, issues, next priorities
- [docs/DEMO_CN.md](docs/DEMO_CN.md): Chinese demo/presentation guide
- [docs/DEMO_REHEARSAL_CN.md](docs/DEMO_REHEARSAL_CN.md): Chinese rehearsal script with short demo commands
- [docs/ARCHITECTURE_OVERVIEW.md](docs/ARCHITECTURE_OVERVIEW.md): concise architecture summary
- [docs/TEST_PLAN.md](docs/TEST_PLAN.md): local validation scope
- [docs/INCREMENTAL_DEMO.md](docs/INCREMENTAL_DEMO.md): focused incremental demo notes
- [docs/DEMO_FLOW.md](docs/DEMO_FLOW.md): end-to-end defense demo flow
- [docs/CHANGELOG.md](docs/CHANGELOG.md): modification history

## Progress Tracking Convention

This repository is maintained as an actively iterating graduation-project backend. Whenever an important feature, runtime fix, or demo-visible behavior is merged or pushed, the following docs should be reviewed and synchronized in the same change set when applicable:

- `README.md`
- `docs/STATUS.md`
- `docs/DEMO_CN.md`
- `docs/CHANGELOG.md`

This is a workflow convention for keeping code status, demo narrative, and repository history aligned over time.

## License

MIT
