# MindDock Thesis Alignment

This document is the canonical wording guide for the thesis, README, and defense demo. It keeps the project description aligned with the current implementation and prevents overclaiming.

MindDock should be described as a local, evidence-first personal knowledge management assistant. It supports grounded RAG workflows, citation/evidence traceability, workflow trace metadata, runtime configuration, Prompt Profiles, trusted built-in Source Skills, and lightweight workspace preferences.

It should not be described as a full commercial NotebookLM replacement, a complete Skill Market, a long-term memory system, or a fully autonomous LangGraph Agent platform.

## Overall Status

Recommended conclusion:

```text
PASS WITH TARGETED BOUNDARIES
```

The project is suitable for thesis writing and defense demonstration if the thesis wording stays honest about partial and future-work capabilities.

## Completed Capabilities

| Capability | Current implementation | Thesis wording |
|---|---|---|
| Text-based PDF ingest | PDF text extraction with source/page/chunk metadata where text is extractable. | The system supports text-based PDF ingestion and preserves page-level evidence metadata. |
| Markdown / TXT ingest | Local Markdown and plain-text files can be chunked, embedded, indexed, searched, and cited. | The system supports local text knowledge-base ingestion for common personal notes. |
| RAG QA loop | Ingest -> chunk -> embedding -> retrieval -> generation -> citation is implemented. | The system implements a complete evidence-grounded RAG question-answering loop. |
| Citation / evidence | Search, chat, summarize, and compare share citation/evidence structures. | The system returns source/page/chunk evidence to improve answer traceability. |
| Workflow trace | Frontend-facing use cases expose retrieval/generation metadata and policy metadata. | The system records observable workflow traces for auditability and demo explanation. |
| Watchdog incremental ingest | Local file changes can be synchronized through watcher-based create/modify/delete/move handling. | The system supports incremental local knowledge-base maintenance. |
| Runtime config | Runtime profile/provider/model boundaries are represented separately from service logic. | The system separates model runtime configuration from RAG service orchestration. |
| Prompt Profile Registry | Chat, summarize, and compare use named/versioned prompt profiles with policy metadata. | The system abstracts generation constraints into auditable Prompt Profiles. |
| Trusted Source Skill control plane | Built-in source handlers are exposed through trusted catalog/API/settings metadata. | The system provides a trusted-only Source Skill control plane for ingestion capabilities. |
| Workspace-local user preference profile | Frontend preferences store task/top_k/style/citation defaults and send sanitized metadata to workflow trace. | The system supports lightweight workspace preference defaults, not long-term memory. |

## Partially Completed Capabilities

| Capability | Current boundary | Safe wording |
|---|---|---|
| Static web extraction | Fetchable static HTML can be extracted; JS-rendered/login/paywalled pages and broad crawling are not supported. | The system supports basic static web page ingestion. |
| CSV rows-as-text | CSV rows can be indexed as text; no formula execution, spreadsheet engine, SQL, or table reasoning engine. | The system supports lightweight CSV text ingestion. |
| OCR text ingest | OCR-derived text can be indexed when OCR is configured; no full multimodal image understanding. | The system supports OCR text ingestion for image-based sources. |
| Audio/video transcript ingest | Transcript text paths, such as sidecar transcripts, can be indexed; native media understanding is not the default capability. | The system supports transcript-based media ingestion. |
| Rerank | Retrieval refinement is heuristic. | The system uses heuristic rerank and leaves cross-encoder rerank as future optimization. |
| Compression | Context reduction is trimming / lexical compression. | The system uses lightweight context trimming and leaves LLM compression as future work. |
| Intent classification | Auto mode uses lightweight rule-based routing. | The system provides limited rule-based task routing. |
| LangGraph workflow | LangGraph is used for retrieval preparation subworkflow orchestration. | LangGraph enhances workflow modularity and observability for retrieval preparation. |

## Future Work

These items should remain future work unless implemented in a later PR:

- Word/Docx ingestion
- complete Skill Market
- remote plugin installation
- plugin signature validation
- sandbox execution and permission isolation
- OpenAPI / MCP tool import
- long-term user memory
- automatic user profiling
- vectorized user preference retrieval
- true cross-encoder reranker
- LLM context compression
- complete LangGraph Agent controller
- commercial NotebookLM-style product ecosystem

## Statements To Avoid

| Avoid | Use instead |
|---|---|
| MindDock implements cross-encoder rerank. | MindDock currently uses heuristic rerank. |
| MindDock implements LLM context compression. | MindDock currently uses trimming / lexical compression. |
| MindDock implements a complete Skill Market. | MindDock implements a trusted-only Source Skill control plane over built-in handlers. |
| MindDock supports remote plugin installation. | Remote install remains future work. |
| MindDock supports sandboxed third-party plugin execution. | Sandboxing and permission isolation remain future work. |
| MindDock implements long-term personalized memory. | MindDock supports workspace-local preference defaults. |
| MindDock automatically infers a user profile. | User profiling remains future work. |
| MindDock uses LangGraph as a full autonomous Agent controller. | MindDock uses LangGraph for a retrieval preparation subworkflow. |
| MindDock is a full NotebookLM replacement. | MindDock is a thesis prototype focused on local evidence-first personal knowledge workflows. |

## Demo-Ready Narrative

A concise defense narrative:

> MindDock is a personal knowledge management assistant built around evidence-first RAG. It can ingest local documents, retrieve relevant chunks, generate grounded answers, and expose citations, evidence, and workflow trace metadata. The system further introduces Prompt Profiles for auditable generation strategy management, a trusted-only Source Skill control plane for explaining source ingestion capabilities, and workspace-local user preferences for repeatable request defaults.

## Defense Demo Route

1. Start the backend and frontend.
2. Show indexed sources in the source list.
3. Add or update a knowledge-base document, then run ingest or watcher sync.
4. Execute chat, summarize, and compare.
5. Show evidence, citations, source/page/chunk references, and workflow trace.
6. Show Settings > Sources for trusted Source Skills.
7. Show Settings > Retrieval / Display for workspace-local preferences.
8. Explain Prompt Profile ids/versions through workflow trace metadata.

## Innovation Mapping

| Engineering capability | Thesis innovation angle |
|---|---|
| Citation-driven RAG | Evidence-grounded answer generation and traceable personal knowledge retrieval. |
| Prompt Profile Registry | Versioned generation policy layer for auditable prompt strategy management. |
| Source Skill trusted-only control plane | Safe, built-in ingestion capability catalog that prepares for future skill ecosystems without enabling arbitrary code execution. |
| Workflow trace | Observable execution metadata for debugging, auditability, and defense explanation. |
| Runtime profile | Runtime/provider/model abstraction for configurable deployment environments. |
| LangGraph retrieval subworkflow | Service-as-node style workflow expression for retrieval preparation, without replacing the main service chain. |
| Future Skill Market | Future extension direction, not a completed implementation. |

## Documentation Cross-References

- `README.md` for current scope and quick start.
- `docs/demo-guide.md` for the shortest defense route.
- `docs/source-skills.md` for trusted Source Skill boundaries.
- `docs/user-preferences.md` for lightweight preference profile boundaries.
- `docs/DEMO_SCRIPT.md` for an expanded repeatable demo script.
