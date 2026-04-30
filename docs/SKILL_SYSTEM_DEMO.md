# Skill System Demo

MindDock source skills are a safe catalog and binding layer for local ingestion capabilities. They describe what MindDock can do without allowing arbitrary local code execution.

## Concepts

- Builtin skills are implemented source extraction capabilities shipped with MindDock, such as `image.ocr`, `csv.extract`, `url.extract`, `audio.transcribe`, and `video.transcribe`.
- Local skills are declaration-only `skill.json` manifests. They can bind a source type to a trusted builtin handler, but they cannot provide Python entrypoints, scripts, subprocess commands, or secrets.
- Trusted handlers are the allowlisted backend contracts that local manifests may reference. Handler IDs match builtin source skill IDs.
- Future skills are disabled catalog entries used for roadmap visibility. They are not executable and should not be resolved for ingestion.

Actual ingestion still runs through `SourceLoaderRegistry` and concrete loaders. Skill bindings add explainable metadata and CLI/demo affordances; they do not replace RAG retrieval or loader execution.

## skill-resolve

Use `skill-resolve` to explain how MindDock would bind a source to a skill:

```bash
conda run -n minddock python -m app.demo skill-resolve --source demo_video.mp4
```

Resolution order:

1. Enabled local source manifests are checked first.
2. If no local manifest matches, implemented builtin source skills are matched by exact source type or file extension.
3. Unsupported extensions return `no_matching_local_skill`.

There is no fuzzy matching by title, domain, or filename content.

## Builtin Fallbacks

Current builtin fallback behavior:

```text
.mp4/.mov/.mkv/.webm  -> video.transcribe
.mp3/.wav/.m4a/.aac/.flac/.ogg -> audio.transcribe
.png/.jpg/.jpeg/.webp -> image.ocr
.csv                  -> csv.extract
http/https URL         -> url.extract
.pdf                  -> file.pdf
.txt                  -> file.text
.md/.markdown         -> file.markdown
```

`.webm` is treated as video by default, matching the media loader. A caller that passes `loader_name=audio.transcribe` may bind `.webm` to audio.

## Local Manifest Precedence

If a local enabled manifest matches the source extension or URL kind, it wins over builtin fallback and its local skill identity is written into chunk metadata.

Disabled local manifests do not block builtin fallback.

## Demo Notes

- Video and audio demos can use sidecar transcripts. See `docs/VIDEO_SKILL_DEMO.md`.
- Image OCR uses the `image.ocr` builtin skill and the configured OCR provider, currently RapidOCR by default.
- CSV sources use `csv.extract`, which converts rows into searchable text with row and column metadata.
- URL extraction is static HTML only. JavaScript rendering is future work.

## Future Work

A future `multimodal_frames` provider should fit under the media source architecture as an additional provider or loader mode, while keeping sidecar transcripts as the highest-priority deterministic demo path.

Expected future additions:

- config keys for provider, frame sampling interval, max frames, max chars, and model/runtime profile
- metadata for provider, sampled frame count, transcript/caption basis, warnings, and whether sidecar or frames were used
- tests for sidecar priority, provider fallback, no binary metadata leaks, and frontend display
- source drawer labels for transcript-only versus frame-aware video processing
