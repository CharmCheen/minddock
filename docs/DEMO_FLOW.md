# Demo Flow

## Purpose

This document is the recommended defense-ready walkthrough for MindDock.

Target flow:

1. build the knowledge base
2. search
3. question answering
4. topic summarization
5. structured Mermaid output
6. incremental maintenance

## Demo Preparation

Before presenting:

1. Ensure at least one `.md`, `.txt`, or `.pdf` file exists under `knowledge_base/`
2. The repository already includes `knowledge_base/example.md` for a fresh-clone demo
3. Rebuild the knowledge base once
4. Start the FastAPI service
5. Optionally start the watcher in a second terminal

Recommended commands:

```powershell
conda env create -f environment.yml
conda activate minddock
python -m app.demo ingest
python -m app.demo serve
```

Optional watcher terminal:

```powershell
conda activate minddock
python -m app.demo watch
```

## Step 1: Full Ingest

Command:

```powershell
python -m app.demo ingest
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

```powershell
python -m app.demo search
```

What to say:

- this shows controlled retrieval from the local knowledge base
- search is currently safest to demo without extra filters
- this is the foundation for grounded answers and summaries

What to point at:

- the returned `hits`
- the `source`
- the returned citation structure

## Step 3: Chat Demo

Example request:

```powershell
python -m app.demo chat
```

What to say:

- the answer is grounded in retrieved evidence rather than open-ended generation
- citations are returned with traceable fields such as `ref`, `section`, and `location`
- even without a real API key, the fallback path still produces a stable demo

What to point at:

- `answer`
- `citations`
- `ref` / `section` / `location`

## Step 4: Summarize Demo

Example request:

```powershell
python -m app.demo summarize
```

What to say:

- this endpoint reuses the same retrieval and citation chain
- the difference from `/chat` is that it produces a concise synthesis instead of a direct answer
- it is still grounded and citation-backed

What to point at:

- `summary`
- `citations`
- `retrieved_count`

Optional upgraded demo:

```powershell
python -m app.demo summarize --mode map_reduce
```

What to say:

- this version first builds partial summaries across grouped evidence and then reduces them into one grounded synthesis
- it is still traceable back to the original citations

Optional Mermaid demo:

```powershell
python -m app.demo summarize --mode map_reduce --output-format mermaid
```

What to point at:

- `structured_output`
- the returned Mermaid text is grounded in retrieved evidence

## Step 5: Structured Output Demo

Use the Mermaid variant above and explain:

- the system can turn grounded evidence into a structured representation for demo/presentation use
- this is a lightweight first version of knowledge-structure output, not yet a full visual reasoning engine

## Step 6: Incremental Update Demo

Best run with watcher in a second terminal:

```powershell
conda activate minddock
python -m app.demo watch
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

- `/chat` and `/summarize` use the mock or fallback provider

Safe explanation:

- the system still demonstrates grounded generation with citations
- the fallback path is intentionally kept for stable offline demos

### Watcher is unstable on the current machine

Symptom:

- file events are delayed or inconsistent

Safe explanation:

- the correctness of incremental logic is covered by unit tests
- watcher is an OS-level bridge and is better treated as a manual demo capability

## Suggested Defense Narrative

You can summarize the project like this:

1. We first build a local knowledge base from Markdown, text, or PDF files.
2. We then perform controlled retrieval on top of that local store.
3. On top of retrieval, we support grounded Q&A with citations.
4. We also support grounded topic summarization with the same citation chain.
5. Finally, we support incremental maintenance so the knowledge base can stay updated as files change.
