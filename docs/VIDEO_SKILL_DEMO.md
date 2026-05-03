# Video Skill Demo

## Current Local ASR Demo Flow

Run `start.bat` first. The startup script is responsible only for reaching a
usable Ready state: Local ASR health ready, backend health ready, Local ASR
provider config saved, faster-whisper model preloaded, model status `ready`,
frontend dev server ready, frontend-to-backend API connectivity ready, and
browser opened.

`start.bat` intentionally does not ingest files, does not call
`/v1/audio/transcriptions`, and does not perform real transcription. Model
preload is not transcription; it only loads the configured model so Settings can
show Local ASR connected / model ready.

Run `run_demo_ingest.bat` separately for the real ingest step. It checks backend
health, Local ASR health, and backend model status before asking the user to
confirm that `knowledge_base` contains a valid `.wav`, `.mp3`, or `.mp4` file
without a same-name sidecar transcript. Prefer `.wav` or `.mp3` for the first
real smoke test, then try `.mp4` after audio smoke passes.

Demo ingest runs rebuild ingest, which recreates Chroma. If the backend is
still running, Windows may keep `data/chroma/chroma.sqlite3` locked. When
`run_demo_ingest.bat` asks, close the `MindDock-Backend` window or manually
release port `8000` before continuing. The script shows:

```bat
netstat -ano | findstr :8000
taskkill /PID <pid> /F
```

It does not kill the backend process automatically.

Do not commit model weights or runtime data. Keep `models/`, `data/`, and
`knowledge_base/` out of the commit unless a future task explicitly changes
that policy.

MindDock supports media transcript ingestion (ASR) by indexing transcript sidecar files, calling an OpenAI-style audio transcription API, or using the bundled local ASR companion server under `tools/local_asr_server`. This is **video transcript / audio transcription**, not video frame understanding. Faster-whisper model weights are not committed to the repository; users can preload/download them through the local ASR server or point the server to a manually downloaded model directory.

## Local ASR Demo Startup

For the Local ASR demo, use two environments:

- `minddock` for the MindDock backend, RAG, Chroma, and ingest commands.
- `local-asr` for `tools/local_asr_server` and `faster-whisper`.

Install Local ASR with:

```bash
conda create -n local-asr python=3.10 -y
conda activate local-asr
pip install -r tools/local_asr_server/requirements.txt
```

`start.bat` starts Local ASR, starts the backend, saves Local ASR config,
preloads the selected model, starts the frontend, and opens the browser. It
does not run ingest, does not call `/v1/audio/transcriptions`, and does not
verify search/chat/citations.

Use `run_demo_ingest.bat` after `start.bat` reaches Model Ready. It checks the
backend, Local ASR health, and model status before running
`python -m app.demo ingest`. Because that command rebuilds Chroma, close the
backend first when the script prompts; if port `8000` is still occupied, the
script stops before ingest.

To avoid accidental online model download during a demo, set:

```bat
set LOCAL_ASR_MODEL_BASE_PATH=D:\models\faster-whisper-base
```

The companion server also supports `LOCAL_ASR_MODEL_SMALL_PATH` and
`LOCAL_ASR_MODEL_MEDIUM_PATH`. A valid local path is used by both model preload
and transcription. If a configured path is invalid, the server reports it and
falls back to normal model-name resolution.

For a first real ASR smoke test, prefer a valid English-name `.wav` file
without a sidecar transcript, for example `knowledge_base/local_asr_smoke.wav`.
Use `.mp3` next and `.mp4` only after audio smoke passes. Avoid very short,
silent, damaged `.mp4` files and avoid Chinese filenames for the first smoke
test. Recommended recording content:

```text
这是 MindDock 本地语音识别测试，系统应该把这段录音转录成文本并入库。
```

This demo is transcript-only ASR; it is not video frame understanding, OCR,
frame extraction, multimodal embedding, or LLM summary.

## Provider Modes

Set via `MEDIA_TRANSCRIPT_PROVIDER` (default: `mock`):

| Provider   | Behavior |
|------------|----------|
| `sidecar`  | Always takes priority when a matching transcript sidecar exists next to the media file |
| `mock`     | Returns deterministic placeholder transcripts; no external dependency |
| `api`      | Calls a remote OpenAI-style audio transcription endpoint (`/audio/transcriptions`) |
| `local`    | Manages a local faster-whisper ASR companion service (auto-start + health-check + model preload) |
| `disabled` | Returns empty text with warning; no media ingestion |

## Supported Media

Video files (`.webm` is treated as video by the current loader):

- `.mp4`
- `.mov`
- `.mkv`
- `.webm`

Audio files:

- `.mp3`
- `.wav`
- `.m4a`
- `.aac`
- `.flac`
- `.ogg`
- `.webm`

## Sidecar Transcript Names (Highest Priority)

Place the media file and transcript in `knowledge_base` with the same stem.

For `knowledge_base/demo_video.mp4`, MindDock checks sidecars in this order:

```text
knowledge_base/demo_video.transcript.md
knowledge_base/demo_video.transcript.txt
knowledge_base/demo_video.txt
knowledge_base/demo_video.vtt
knowledge_base/demo_video.srt
```

When a recognized sidecar exists next to a matching media file, it **always takes priority** over mock, API, or disabled providers. MindDock skips indexing that sidecar as a separate standalone text source. Ordinary `.txt` and `.md` files that are not sidecars are still indexed normally.

`.srt` and `.vtt` timing, index, header, and cue metadata are stripped before indexing.

## API Provider Configuration

### Option 1: Frontend (Recommended)

Open **Settings → Runtime → Media Transcript Provider**, select `api` or `local` as the provider, fill in the fields, then click **Save**. The API key is stored only in `os.environ`; other fields are persisted to `data/active_media_transcript.json`.

### Option 2: Environment Variables

Set these environment variables **before starting the backend**:

```powershell
$env:MEDIA_TRANSCRIPT_PROVIDER="api"
$env:MEDIA_TRANSCRIPT_API_KEY="your_api_key_here"
$env:MEDIA_TRANSCRIPT_API_BASE_URL="https://api.openai.com/v1"
$env:MEDIA_TRANSCRIPT_MODEL="whisper-1"
$env:MEDIA_TRANSCRIPT_TIMEOUT_SECONDS="60"
```

- `MEDIA_TRANSCRIPT_API_KEY` — your API key (never commit to the repository)
- `MEDIA_TRANSCRIPT_API_BASE_URL` — base URL or full endpoint; the code appends `/audio/transcriptions` if not already present
- `MEDIA_TRANSCRIPT_MODEL` — model name (default: `whisper-1`)
- `MEDIA_TRANSCRIPT_TIMEOUT_SECONDS` — HTTP request timeout (default: `60`)

The API provider expects an OpenAI-compatible response format:

```json
{"text": "...transcript text..."}
```

**Important**: After changing environment variables or saving via the frontend, restart the backend. Media files that were already ingested must be re-ingested to use the new transcript provider.

### Config Priority

The effective media transcript config is resolved in this order:

1. **UI active config** (`data/active_media_transcript.json` + `os.environ` for api_key)
2. **Settings** (from `.env` or `Settings` object)
3. **os.environ** (raw environment variables)
4. **Defaults** (provider=`mock`, model=`whisper-1`, timeout=60s)

Sidecar transcripts always take priority over any provider setting.

### API Fallback Behavior

If any of the following occurs, the API provider falls back to `mock` with a warning:

- `MEDIA_TRANSCRIPT_API_KEY` or `MEDIA_TRANSCRIPT_API_BASE_URL` is empty
- HTTP 4xx / 5xx response from the API
- Request timeout
- Network / connection error
- Unparseable JSON response
- Empty transcript text in the API response

The API key is never written to metadata, warnings, or logs.

## Ingest

```bash
conda run -n minddock python -m app.demo ingest --no-rebuild
```

After ingest, the video source is indexed using transcript text. In the source drawer, representative metadata should show:

- `Video source`
- `video.transcribe` (loader name badge)
- `Transcript: sidecar` (or `Transcript: api` / `mock` / `disabled`)
- `Basis: transcript text`
- media filename
- sidecar filename (if sidecar was used)

The source list also shows a `Transcript: {provider}` badge for ready video/audio sources.

## Derived Content (Summary & Outline)

When `MEDIA_TRANSCRIPT_DERIVED_ENABLED=true` and the transcript is long enough (≥ `MEDIA_TRANSCRIPT_DERIVED_MIN_CHARS`, default 400), the ingest pipeline generates two additional derived chunks:

- **media_summary** — extractive summary (up to `MEDIA_TRANSCRIPT_DERIVED_SUMMARY_MAX_CHARS` chars)
- **media_outline** — extractive outline (up to `MEDIA_TRANSCRIPT_DERIVED_OUTLINE_MAX_ITEMS` items)

These are deterministic/extractive — no LLM calls, no video frame analysis.

### Frontend Display

- **Source Drawer**: A "Derived Content" section appears when derived chunks exist, showing the summary and outline with "Derived from transcript" labels and an "Extractive / deterministic" badge.
- **Source List**: Green `Summary` and `Outline` badges appear next to the transcript provider badge.

### Eligibility

Only media sources with `transcript_provider` of `sidecar`, `api`, or `local` are eligible. Mock and disabled providers are skipped. If the transcript is too short, derived chunks are not generated.

## Frontend Visibility

Open **Settings → Runtime** to see the editable **Media Transcript Provider** editor. It shows:

- Provider selector (`api`, `local`, `mock`, `disabled`)
- Enabled toggle
- Remote API fields: Base URL, API Key, Model, Timeout
- Local ASR fields: Server Path, Host, Port, Model, Device, Compute Type, Auto Start, Timeout
- **Check Status** / **Start Local ASR** buttons — 检查/启动本地服务
- **Check Model** / **Preload Model** buttons — 检查/预加载 faster-whisper 模型
- Capability: **Transcript-only ASR**
- Limitations: no frame understanding, no multimodal embedding
- Config source: `ui_override` (when saved via frontend) or `environment` (when using env vars only)

**Save** persists non-secret fields to `data/active_media_transcript.json`; the API key is stored only in `os.environ`. **Reset** removes the active config file and clears UI-set env vars. Note: Reset clears the UI override and current backend-session key. If you rely on shell environment variables (`MEDIA_TRANSCRIPT_API_KEY` etc.), restart the backend or reconfigure as needed. **Test Config** validates the current form values for completeness; it does not perform a real transcription.

**Local ASR Recommended Flow**:
1. Save settings
2. Start Local ASR
3. Check Status
4. Preload Model
5. Wait until Ready
6. Run ingest

Preload Model 会让 `local_asr_server` 加载选中的模型。首次 preload 可能从 HuggingFace 下载模型（small ~500MB）。3050 Laptop 4GB 推荐 `small`/`base` + `int8`。

The effective config priority is: **UI active config > Settings > os.environ > defaults**. Sidecar transcripts always take priority regardless of provider setting.

## Skill Resolve Demo

```bash
conda run -n minddock python -m app.demo skill-resolve --source demo_video.mp4
```

The command should resolve to the builtin `video.transcribe` binding when no local manifest overrides it.

## Notes

- Retrieval uses transcript text only.
- This is **video transcript ingestion (ASR)**, not video frame understanding, OCR, or multimodal video analysis.
- Ready video sources remain selectable as normal sources.
- Pending and failed source behavior is unchanged.
- No large media files should be committed to git.
- The sidecar transcript path remains the most stable demo path.

## Quick Demo Runbook

Reproducible steps to verify the full media transcript derived-chunks pipeline.

### Prerequisites

- `knowledge_base/demo_video.mp4` — a small video file (any size, not used for frame analysis)
- `knowledge_base/demo_video.transcript.md` — a sidecar transcript (≥ 400 chars recommended)

### Step 1: Enable derived chunks

```powershell
$env:MEDIA_TRANSCRIPT_DERIVED_ENABLED="true"
$env:MEDIA_TRANSCRIPT_DERIVED_MIN_CHARS="100"
$env:MEDIA_TRANSCRIPT_DERIVED_MAX_INPUT_CHARS="20000"
$env:MEDIA_TRANSCRIPT_DERIVED_SUMMARY_MAX_CHARS="800"
$env:MEDIA_TRANSCRIPT_DERIVED_OUTLINE_MAX_ITEMS="8"
```

### Step 2: Ingest

```bash
conda run -n minddock python -m app.demo ingest
```

Verify in the output that `demo_video.mp4` appears in `ingested_sources` and chunk count increases by 2 (summary + outline) compared to a non-derived ingest.

### Step 3: Start backend and frontend

```bash
# Terminal 1
conda run -n minddock python -m app.demo serve --port 8000

# Terminal 2
cd frontend
npm run dev
```

### Step 4: Verify in frontend

**Settings → Runtime**: Media Transcript Provider card should show:
- Capability: Transcript-only ASR
- Limitations: no frame understanding

**Source List**: `demo_video` should show:
- `Transcript: sidecar` badge
- `Summary` badge
- `Outline` badge

**Source Drawer** (click demo_video):
- `video.transcribe` loader badge
- `Basis: transcript text`
- **Derived Content** section with:
  - Transcript Summary (extractive)
  - Transcript Outline (extractive)
  - "Extractive / deterministic" badge
  - "This does not perform frame-level video understanding."
- Raw transcript chunks still visible below

### Step 5: Test retrieval

Ask these questions in the chat panel:

1. `demo video 里提到了什么 smoke test？`
2. `这个视频的 summary 和 outline 讲了什么？`

Expected: answers cite `demo_video.mp4`, derived chunks appear in retrieval results.

### What this proves

```text
视频文件 → sidecar transcript → raw transcript chunk
→ derived summary chunk (extractive, deterministic)
→ derived outline chunk (extractive, deterministic)
→ frontend Source Drawer 可展示
→ RAG search 可命中 derived chunks
→ citation 指向原始视频源
```

This is **not** video frame understanding, multimodal analysis, or LLM-generated summarization.
