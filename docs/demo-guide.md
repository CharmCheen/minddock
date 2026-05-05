# MindDock Defense Demo Guide

This guide is the shortest stable route for a thesis-defense demo. It presents MindDock as a local, evidence-first personal knowledge assistant with grounded RAG, citations, workflow trace, runtime configuration, Prompt Profiles, trusted Source Skills, and workspace-local user preferences.

It intentionally avoids claiming that MindDock is a full commercial NotebookLM replacement, a complete Skill Market, or a long-term memory system.

## Local Startup

Activate the backend environment:

```powershell
conda activate minddock
```

Start the backend:

```powershell
python -m app.demo serve
```

Start the frontend:

```powershell
cd frontend
npm run dev
```

Open:

```text
http://localhost:5173
```

Health check:

```powershell
curl http://127.0.0.1:8000/health
```

## Prepare Demo Sources

Use local files that are safe to show during the defense. Recommended:

- one Markdown or TXT note
- one text-based PDF
- optionally one static URL source
- optionally one CSV file for rows-as-text ingest
- optionally one image for OCR text ingest
- optionally one audio/video file with a transcript sidecar

Index local sources:

```powershell
python -m app.demo ingest --no-rebuild
```

For a watcher demonstration, run one bounded sync:

```powershell
python -m app.demo watch --once
```

Use the continuous watcher only when you want to show live incremental updates:

```powershell
python -m app.demo watch --path knowledge_base
```

## Shortest Defense Route

1. Start backend and frontend.
2. Open Sources and show indexed documents.
3. Add or update a knowledge-base document, then run ingest or watcher sync.
4. Run Chat, Summarize, and Compare from the frontend.
5. Show evidence, citation, source, page, chunk, and workflow trace metadata.
6. Show the supporting control surfaces:
   - Settings > Models & Runtime for runtime configuration.
   - Settings > Sources for trusted built-in Source Skills.
   - Settings > Retrieval / Display for workspace-local user preferences.
   - Workflow trace metadata for Prompt Profile ids and versions.

## Task Demonstrations

### Chat

Ask a question that is clearly answerable from the indexed documents.

Expected observation:

- answer is grounded in retrieved context
- citations are returned
- evidence/source/page/chunk data can be inspected
- insufficient-evidence behavior can be shown with an unrelated question

### Summarize

Summarize a topic covered by multiple sources.

Expected observation:

- summary uses retrieved evidence
- citations remain visible
- workflow trace shows retrieval and prompt profile metadata

### Compare

Ask for a comparison across sources.

Expected observation:

- output separates common points, differences, and conflicts when available
- citations remain attached to the underlying evidence
- the prompt profile is the grounded compare JSON profile

## Feature Wording For The Defense

Completed:

- text-based PDF, Markdown, and TXT ingest
- RAG question-answering loop
- citation / evidence / workflow trace
- watchdog incremental ingest
- runtime config
- Prompt Profile Registry
- trusted-only Source Skill control plane
- workspace-local user preference profile

Partially completed:

- static web page body extraction
- CSV rows-as-text
- OCR text ingest
- audio/video transcript-text ingest
- heuristic rerank
- trimming / lexical compression
- LangGraph retrieval subworkflow

Future work:

- Word/Docx ingest
- complete Skill Market
- remote plugin install
- plugin signature validation
- sandbox execution
- OpenAPI / MCP tool import
- long-term user memory
- automatic user profiling
- true cross-encoder reranker
- LLM context compression
- complete LangGraph Agent controller

## Overclaiming To Avoid

Use these boundaries consistently:

| Do not say | Say instead |
|---|---|
| MindDock implements cross-encoder rerank. | MindDock currently uses heuristic rerank. |
| MindDock implements LLM context compression. | MindDock currently uses trimming / lexical compression. |
| MindDock has a complete Skill Market. | MindDock has a trusted-only Source Skill control plane. |
| MindDock has long-term user memory. | MindDock has workspace-local user preference defaults. |
| MindDock is a full LangGraph Agent system. | MindDock uses LangGraph for a retrieval preparation subworkflow. |
| MindDock replaces NotebookLM commercially. | MindDock is a local thesis prototype focused on evidence-first personal knowledge workflows. |

## Useful API Checks

```powershell
curl http://127.0.0.1:8000/sources
curl http://127.0.0.1:8000/frontend/source-skills
```

User preferences are stored in the frontend workspace settings and are visible through request workflow trace metadata, not through a standalone preferences API.

```powershell
curl -X POST http://127.0.0.1:8000/chat `
  -H "Content-Type: application/json" `
  -d '{"query":"What does this knowledge base say about RAG?","top_k":3}'
```

```powershell
curl -X POST http://127.0.0.1:8000/summarize `
  -H "Content-Type: application/json" `
  -d '{"topic":"RAG","top_k":5,"mode":"basic"}'
```

```powershell
curl -X POST http://127.0.0.1:8000/compare `
  -H "Content-Type: application/json" `
  -d '{"question":"Compare the approaches described in the indexed documents.","top_k":6}'
```
