# Source Skill Contract

## What is the Source Skill Contract

The **Source Skill Contract** is a lightweight, read-only descriptive layer that explains how MindDock turns external sources into normalized text for the RAG pipeline.

It is NOT a general-purpose skill runtime. It does NOT execute code, invoke LLMs, or manage agent plans. It simply answers:

- What source extraction capabilities are built in?
- What does each skill accept and produce?
- What are its limitations and provider options?

## Why MindDock Does Not Build a Full Agent Skill Runtime

A full Agent Skill Runtime would require:

- Arbitrary code execution boundaries
- LLM-driven skill selection and planning
- Community plugin sandboxing
- Multi-turn skill orchestration
- Cross-session memory and state management

These are out of scope for the current graduation-project timeline and would introduce security and maintenance risks that are better addressed after the core RAG pipeline is stable.

Instead, MindDock keeps source extraction deterministic:

- `SourceLoaderRegistry` resolves loaders by `source_type` and extension.
- Loaders implement `supports()` and `load()`.
- Output is always `SourceLoadResult`.
- The catalog only **describes** this behavior, it does not change it.

## Source Skill Input / Output

### Input

A `SourceDescriptor` carrying:

- `source` — stable identity string
- `source_type` — e.g. `file`, `url`
- `local_path` — for file sources
- `requested_source` — for URL redirect tracking

### Output

`SourceLoadResult` with:

- `descriptor` — the resolved descriptor (may differ from input after redirects)
- `title` — human-readable title
- `text` — normalized plain text for chunking and embedding
- `metadata` — source-specific metadata (e.g. `source_media`, `source_kind`, `loader_name`, `page_blocks`)
- `warnings` — loader-level diagnostics such as `empty_main_text` or `ocr_mock_fallback`

### Metadata Contract

Loaders are encouraged to set these fields when applicable:

- `source_media`: `text` | `image` | `audio` | `video`
- `source_kind`: `pdf_file` | `markdown_file` | `text_file` | `web_page` | `image_file`
- `loader_name`: stable identifier such as `url.extract` or `image.ocr`
- `loader_warnings`: comma-separated warning codes stored in chunk metadata
- `retrieval_basis`: how the source is later retrieved, e.g. `ocr_text`

### Warnings Contract

Warnings are short, enum-like strings:

- They do NOT become chunk body text.
- They do NOT affect embedding input.
- They are exposed in chunk metadata for debugging and UI indicators.

Examples:

- `empty_main_text`
- `canonical_missing`
- `title_missing`
- `ocr_mock_fallback`
- `ocr_empty`
- `non_html_content_type`

## Implemented Source Skills

These skills are present in the active built-in catalog (`app.rag.source_skill_catalog`):

| id | input | source_media | loader_name | key capabilities |
|---|---|---|---|---|
| `file.pdf` | `.pdf` | `text` | `pdf.parse` | text extraction, page metadata, chunking, citation page support |
| `file.markdown` | `.md`, `.markdown` | `text` | `markdown.read` | markdown text, heading structure |
| `file.text` | `.txt` | `text` | `text.read` | plain text |
| `url.extract` | `url` | `text` | `url.extract` | static HTML, title/body extraction, canonical URL, meta description |
| `csv.extract` | `.csv` | `text` | `csv.extract` | CSV rows as text, header detection, row limit |
| `image.ocr` | `.png`, `.jpg`, `.jpeg`, `.webp` | `image` | `image.ocr` | OCR text, mock fallback, optional RapidOCR |

The `csv.extract` skill was added after the initial Source Skill Contract to validate that the contract extension path works: a new source type can be implemented in its own module (`app.rag.source_skills.csv_skill`), registered in `SourceLoaderRegistry`, described in the catalog, and immediately usable by the existing ingest, chunking, retrieval, and citation pipeline without modifying retrieval, rerank, citation, or frontend code.

## Future Extension (Not in Active Catalog)

The following are documented future directions. They do NOT appear in the built-in catalog because they are not yet implemented.

| id | description | why not yet |
|---|---|---|
| `image.caption` | Generate descriptive captions for images | Requires multimodal LLM or vision model |
| `audio.transcribe` | Speech-to-text for audio files | Requires Whisper or similar ASR backend |
| `video.transcribe` | Extract speech and optionally scene descriptions from video | Requires ASR + keyframe extraction pipeline |
| `url.js_rendered` | Fetch JavaScript-rendered pages | Requires headless browser infrastructure |

## Integration Patterns

### SourceSkill → MCP-style Integration (Future)

If MindDock later exposes source skills via MCP (Model Context Protocol), the contract would map naturally:

- MCP `tool` name = `SourceSkillInfo.id`
- MCP `input_schema` = `SourceDescriptor` fields
- MCP `output` = `SourceLoadResult.to_api_dict()` (without secrets)

This is a documentation-only mapping today.

## Security Boundaries

The Source Skill Contract enforces these boundaries by design:

1. **No arbitrary code execution** — the catalog contains only frozen dataclasses; there is no `execute()` method.
2. **No community plugin execution by default** — there is no disk scan or dynamic import for unknown skills.
3. **No LLM autonomous skill execution** — LLMs never decide which loader to run; `SourceLoaderRegistry` uses deterministic `supports()` checks.
4. **No hidden prompts or API keys in metadata** — `SourceSkillInfo` explicitly excludes secrets.

## Graduation Project Positioning

Current implementation:

- **OCR-first multimodal ingestion** via `image.ocr` with mock fallback and optional RapidOCR.
- **URL extraction** proves the `SourceLoaderRegistry` can be extended beyond local files.
- **CSV extraction** (`csv.extract`) validates the Source Skill Contract extension path end-to-end: CSV → `SourceLoadResult` → chunking → Chroma → retrieval → citation.
- **Source Skill Contract** provides the engineering justification for future audio/video/image caption skills without requiring them to be implemented now.

What this means for the thesis:

> "MindDock introduces a Source Skill Contract that normalizes heterogeneous sources into a unified `SourceLoadResult`. The current system implements text, PDF, URL, and image OCR source skills, with the contract designed to accommodate audio transcription and video transcription as future API-backed skills."
