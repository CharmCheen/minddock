# MindDock Demo Script

This is a repeatable demo route for the MindDock thesis defense. It focuses on source ingestion, source-scoped RAG, citations, workflow trace, Prompt Profiles, trusted Source Skills, workspace-local user preferences, image OCR, media transcript ingestion, schedule-candidate extraction, frontend run control, and `skill-resolve`.

The goal is to show a stable local knowledge assistant workflow without depending on fragile live services during the presentation.

## Current Defense Focus

Use the following product boundary consistently:

- Completed: text-based PDF / Markdown / TXT ingest, RAG QA, citations, evidence, workflow trace, watchdog ingest, runtime config, media transcript configuration, Prompt Profile Registry, trusted-only Source Skill control plane, frontend unified execution/run control, and workspace-local user preferences.
- Partial: static web extraction, CSV rows-as-text, OCR text ingest, audio/video transcript-text ingest through sidecar/API/local ASR, schedule-candidate extraction as reviewable candidates, heuristic rerank, trimming compression, and LangGraph retrieval subworkflow.
- Future work: Word/Docx, complete Skill Market, remote plugin install, signatures, sandboxing, OpenAPI/MCP tool import, long-term memory, automatic user profiling, production calendar sync, cross-encoder rerank, LLM context compression, and a complete LangGraph Agent controller.

Do not describe Source Skills as a third-party plugin marketplace, user preferences as long-term memory, heuristic rerank as cross-encoder rerank, or trimming as LLM compression.

## Pre-Demo Checklist

Activate the backend environment:

```bash
conda activate minddock
```

Start the backend:

```bash
python -m app.demo serve
```

Start the watcher only if you want file changes to sync while presenting:

```bash
python -m app.demo watch --path knowledge_base
```

The server does not automatically start the watcher. For the most predictable route, run ingest manually before the demo.

Start the frontend:

```bash
cd frontend
npm install
npm run dev
```

Confirm settings load the local `.env` or default RapidOCR configuration:

```bash
python -c "from app.core.config import get_settings; get_settings.cache_clear(); s=get_settings(); print(s.image_ocr_enabled, s.image_ocr_provider)"
```

Expected:

```text
True rapidocr
```

Confirm the OCR client:

```bash
python -c "from app.rag.image_loader import build_ocr_client; print(type(build_ocr_client()).__name__)"
```

Expected:

```text
RapidOcrClient
```

## Demo Assets

Prepare local assets in `knowledge_base`. These are local demo files and should not be committed.

Recommended assets:

- at least one PDF or text document
- one URL source added through the UI, if already available
- one screenshot image, such as `knowledge_base/<image>.jpg` or `knowledge_base/<image>.png`
- one video sidecar pair:

```text
knowledge_base/demo_video.mp4
knowledge_base/demo_video.transcript.md
```

Example `demo_video.transcript.md`:

```markdown
# Demo Video Transcript

This video introduces MindDock's video skill demo.

It explains that MindDock can index video files through sidecar transcripts.

The transcript is stored as searchable chunks in the local vector database.

Users can select the video source and ask questions with citations.
```

Notes:

- Do not commit `knowledge_base` demo assets.
- The sidecar transcript is intentionally local demo data.
- Real ASR is not required for this stable demo.
- If Local ASR is part of the demo, use `docs/LOCAL_ASR_PROVIDER.md` and `docs/VIDEO_SKILL_DEMO.md` for the explicit setup path.
- More details are in `docs/VIDEO_SKILL_DEMO.md`.

## Ingest And Validation

Run ingest without rebuilding Chroma:

```bash
python -m app.demo ingest --no-rebuild
```

This indexes current local sources while preserving the existing local vector store.

Run `skill-resolve` smoke checks:

```bash
python -m app.demo skill-resolve --source demo_video.mp4
python -m app.demo skill-resolve --source screenshot.jpg
python -m app.demo skill-resolve --source table.csv
python -m app.demo skill-resolve --source https://example.com
python -m app.demo skill-resolve --source archive.zip
```

Expected:

```text
demo_video.mp4      -> video.transcribe
screenshot.jpg      -> image.ocr
table.csv           -> csv.extract
https://example.com -> url.extract
archive.zip         -> no match
```

Optional source inspection:

```bash
python -m app.demo sources
python -m app.demo source-chunks --source demo_video.mp4 --limit 5
```

For the video source, look for metadata such as `source_media=video`, `transcript_provider=sidecar`, `media_filename`, and `transcript_sidecar_filename`.

## Frontend Demo Route

1. Open the source list.

   Show that MindDock can manage multiple source types in one workspace.

2. Show a normal document source.

   Use a PDF or text source to establish the baseline RAG workflow.

3. Open an image source drawer.

   Point out Image/OCR-related metadata if visible. Explain that RapidOCR is the default OCR provider, and that long screenshot reading order and vertical slicing were improved for better ingestion.
   Keep the wording honest: OCR is improved, but dense tables, tiny text, or unusual screenshot layouts can still produce imperfect text.

4. Open the video source drawer.

   Show:

   ```text
   Video source
   Transcript: sidecar
   Media: demo_video.mp4
   Sidecar: demo_video.transcript.md
   ```

5. Select the video source.

6. Ask:

   ```text
   这个视频主要讲了什么？
   ```

   The answer should be grounded in the transcript sidecar.

7. Select the image OCR source.

8. Ask:

   ```text
   这张截图中主要比较了哪些模型？
   ```

   The answer should use OCR text from the selected image source.

9. Select multiple sources.

10. Ask a source-scoped question and show citations.

    Use the citation panel to show which chunks supported the answer.

11. Optional: open Settings > Runtime > Media Transcript Provider.

    Show the transcript provider boundary: `sidecar`, `api`, `local`, `mock`, and `disabled` are transcript-text paths, not video frame understanding.

12. Optional: run schedule-candidate extraction.

    Show that schedule extraction produces candidates that the user can confirm or dismiss before any future calendar sync.

## Source-Scoped Retrieval And Citations

When sources are selected, retrieval is scoped to those selected sources. Multi-source scoped retrieval queries selected sources reliably instead of relying on broad all-source retrieval followed by post-filtering.

In the demo:

- select one source and ask a focused question
- select two sources and ask a comparison question
- show that citations come from selected source chunks
- if the selected sources do not contain enough evidence, the system should avoid overclaiming

This is an important trust point: source selection should mean the answer is grounded in that source scope.

## Skill System Demo

List builtin and local source skills:

```bash
python -m app.demo skills
```

List trusted handler contracts:

```bash
python -m app.demo skill-handlers
```

Resolve representative sources:

```bash
python -m app.demo skill-resolve --source demo_video.mp4
python -m app.demo skill-resolve --source screenshot.jpg
```

Explain:

- builtin skills describe implemented source capabilities such as `image.ocr`, `video.transcribe`, and `csv.extract`
- local manifests can override matching behavior where configured
- actual loading is performed by trusted loaders and handlers
- the skill system does not execute arbitrary local code

More details are in `docs/SKILL_SYSTEM_DEMO.md`.

## Failure And Fallback Plan

If image OCR shows placeholder text:

- check that settings report `True rapidocr`
- check that `build_ocr_client()` returns `RapidOcrClient`
- confirm RapidOCR dependencies are installed in the active environment

If the video appears but transcript metadata says `mock`:

- check that the sidecar filename exactly matches the media stem
- preferred name: `demo_video.transcript.md`
- rerun `python -m app.demo ingest --no-rebuild`

If `demo_video.transcript.md` appears as a standalone source:

- the file may not be recognized as a sidecar
- confirm the sibling media file is named `demo_video.mp4`
- confirm both files are in the same directory

If the watcher does not process new files:

- remember that `serve` does not auto-start the watcher
- run `python -m app.demo watch --path knowledge_base`
- or run `python -m app.demo ingest --no-rebuild`

If the frontend drawer shows old chunks:

- refresh the browser
- restart the backend if needed
- rerun `python -m app.demo ingest --no-rebuild`

If runtime API key behavior is confusing:

- API keys are session-only and are not persisted to disk
- after restarting the backend, re-enter the key or set `LLM_API_KEY` in the backend environment
- source ingestion and `skill-resolve` demos do not require an LLM API key

If schedule candidates are empty:

- confirm the indexed text contains explicit dates or time-like phrases
- run `POST /frontend/schedule-candidates/scan` or the frontend schedule extraction action
- explain that the current feature is candidate extraction and review, not automatic calendar writing

## Recommended 5-Minute Route

```text
0:00-0:30  Architecture and source list
0:30-1:30  Image OCR source and drawer metadata
1:30-3:00  Video sidecar source, drawer metadata, and transcript QA
3:00-3:40  Media Transcript Provider boundary or Local ASR status
3:40-4:20  skill-resolve CLI for video, image, CSV, URL, and unsupported source
4:20-5:00  Source-scoped QA, citations, and optional schedule candidates
```

Keep the narrative simple: MindDock turns local sources into searchable evidence, scopes retrieval to user-selected sources, and cites the chunks it used.

## Notes And Future Work

The video sidecar path is the most stable demo path. It is deterministic, local, and does not require real ASR. Local ASR and remote transcription are available configuration paths, but they should be demonstrated only after the provider reports ready.

Future work can add a `multimodal_frames` provider:

```text
video.mp4
-> sample frames
-> vision model analysis
-> visual transcript
-> Chroma
-> source drawer metadata
-> RAG QA
```

Multimodal video-frame analysis is intentionally not required for this stable thesis demo.
