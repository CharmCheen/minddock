# Demo Flow

## Purpose

This document is the recommended defense-ready walkthrough for MindDock.

Target flow:

1. build the knowledge base
2. search
3. question answering
4. topic summarization
5. incremental maintenance

## Demo Preparation

Before presenting:

1. Ensure at least one `.md` or `.txt` file exists under `knowledge_base/`
2. The repository already includes `knowledge_base/example.md` for a fresh-clone demo
3. Rebuild the knowledge base once
4. Start the FastAPI service
5. Optionally start the watcher in a second terminal

Recommended commands:

```bash
python -m app.rag.ingest --rebuild
uvicorn app.main:app --reload
```

Optional watcher terminal:

```bash
set WATCH_ENABLED=true
python -m app.rag.watcher
```

## Step 1: Full Ingest

Command:

```bash
python -m app.rag.ingest --rebuild
```

What to say:

- this step performs a full rebuild of the local knowledge base
- documents are split into chunks, embedded, and stored in Chroma
- this is the safe baseline before a defense demo
- the bundled `knowledge_base/example.md` is enough for a minimal walkthrough

What success looks like:

- terminal prints `Loaded ...`, `Created ...`, `Stored to Chroma`

## Step 2: Search Demo

Example request:

```bash
curl -X POST http://127.0.0.1:8000/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "storage design",
    "top_k": 3,
    "filters": {
      "source": "notes.md"
    }
  }'
```

What to say:

- this shows controlled retrieval from the local knowledge base
- filters can restrict the search scope by source or section
- this is the foundation for grounded answers and summaries

What to point at:

- the returned `hits`
- the `source`
- the difference between filtered and unfiltered retrieval

## Step 3: Chat Demo

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

What to say:

- the answer is grounded in retrieved evidence rather than open-ended generation
- citations are returned with traceable fields such as `ref`, `section`, and `location`
- even without a real API key, the mock path still produces a stable demo

What to point at:

- `answer`
- `citations`
- `ref` / `section` / `location`

## Step 4: Summarize Demo

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

What to say:

- this endpoint reuses the same retrieval and citation chain
- the difference from `/chat` is that it produces a concise synthesis instead of a direct answer
- it is still grounded and citation-backed

What to point at:

- `summary`
- `citations`
- `retrieved_count`

## Step 5: Incremental Update Demo

Best run with watcher in a second terminal:

```bash
set WATCH_ENABLED=true
python -m app.rag.watcher
```

Then perform these actions under `knowledge_base/`:

1. create a new file
2. modify an existing file
3. delete a file

What to say:

- full ingest is for baseline rebuilds
- incremental maintenance is for per-file updates
- watcher only forwards file events; the real update logic lives in the incremental ingest service

What to point at:

- create: new chunks appear for the new file
- modify: only the changed file is rebuilt
- delete: chunks for that file are removed

## Common Failure Points

### No real embedding model

Symptom:
- ingest prints a warning and falls back to `DummyEmbedding`

Safe explanation:

- the demo still works end-to-end
- retrieval quality is reduced
- this is a runtime fallback, not a pipeline failure

### No API key

Symptom:
- `/chat` and `/summarize` use the mock provider

Safe explanation:

- the system still demonstrates grounded generation with citations
- the mock path is intentionally kept for stable offline demos

### Watcher is unstable on the current machine

Symptom:
- file events are delayed or inconsistent

Safe explanation:

- the correctness of incremental logic is covered by unit tests
- watcher is an OS-level bridge and is better treated as a manual demo capability

## Suggested Defense Narrative

You can summarize the project like this:

1. We first build a local knowledge base from Markdown or text files.
2. We then perform controlled retrieval with optional metadata filters.
3. On top of retrieval, we support grounded Q&A with citations.
4. We also support grounded topic summarization with the same citation chain.
5. Finally, we support incremental maintenance so the knowledge base can stay updated as files change.
