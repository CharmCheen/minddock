# Architecture Overview

## Purpose

This document describes the current repository as it actually exists today.
It is intentionally short and aligned to the implemented code, not an ideal future design.

## Main Modules

### API Layer

Files:

- `app/main.py`
- `app/api/routes.py`
- `app/api/schemas.py`

Responsibilities:

- expose `/search`, `/chat`, `/summarize`, `/health`
- validate request and response payloads
- keep filter semantics consistent across endpoints

### Service Layer

Files:

- `app/services/search_service.py`
- `app/services/chat_service.py`
- `app/services/summarize_service.py`
- `app/services/grounded_generation.py`

Responsibilities:

- `search_service`: query embedding + vector retrieval
- `chat_service`: grounded answer generation + citations
- `summarize_service`: grounded topic summarization + citations
- `grounded_generation`: shared helpers for context assembly, citation building, and evidence selection

### RAG / Storage Layer

Files:

- `app/rag/ingest.py`
- `app/rag/splitter.py`
- `app/rag/embeddings.py`
- `app/rag/vectorstore.py`
- `app/rag/incremental.py`
- `app/rag/watcher.py`
- `app/rag/postprocess.py`

Responsibilities:

- `ingest.py`: full rebuild of the knowledge base
- `splitter.py`: chunk text by section and token window
- `embeddings.py`: sentence-transformers or deterministic fallback embedding
- `vectorstore.py`: Chroma access and filter translation
- `incremental.py`: per-file create / modify / delete maintenance
- `watcher.py`: file-event bridge into incremental maintenance
- `postprocess.py`: rerank / compress placeholders

### Provider Layer

Files:

- `app/llm/factory.py`
- `app/llm/mock.py`
- `app/llm/openai_compatible.py`

Responsibilities:

- choose the active LLM provider
- provide a stable no-key mock path
- optionally call an OpenAI-compatible backend

## Main Data Flow

### Full Build

```text
knowledge_base/*
  -> ingest.py
  -> splitter.py
  -> embeddings.py
  -> vectorstore.py (Chroma)
```

### Search

```text
/search
  -> schemas.py
  -> routes.py
  -> search_service.py
  -> embeddings.py
  -> vectorstore.py
```

### Chat

```text
/chat
  -> schemas.py
  -> routes.py
  -> chat_service.py
  -> search_service.py
  -> grounded_generation.py
  -> llm provider
  -> citations
```

### Summarize

```text
/summarize
  -> schemas.py
  -> routes.py
  -> summarize_service.py
  -> search_service.py
  -> grounded_generation.py
  -> llm provider
  -> citations
```

## Where Filters Are Handled

Filter input enters at:

- `app/api/schemas.py`

Filter forwarding happens in:

- `app/api/routes.py`
- `app/services/search_service.py`
- `app/services/chat_service.py`
- `app/services/summarize_service.py`

Filter execution happens in:

- `app/rag/vectorstore.py`

Current supported fields:

- `source`
- `section`

## Where Citations Are Built

Citation metadata is first created during ingest in:

- `app/rag/ingest.py`

Citation objects for API responses are built in:

- `app/services/grounded_generation.py`

Current exposed citation fields:

- `doc_id`
- `chunk_id`
- `source`
- `snippet`
- `title`
- `section`
- `location`
- `ref`

## Incremental Maintenance Relationship

The intended layering is:

```text
watcher.py
  -> incremental.py
  -> vectorstore.py
```

Meaning:

- `watcher.py` should stay thin
- `incremental.py` owns correctness for create / modify / delete handling
- tests focus mainly on `incremental.py`
- watcher is mainly a manual demo path
