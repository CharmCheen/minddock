# Video Skill Demo

MindDock supports media transcript ingestion (ASR) by indexing transcript sidecar files or calling an OpenAI-style audio transcription API. This is **video transcript / audio transcription**, not video frame understanding. No browser rendering, ffmpeg, Whisper local model, or video player is included.

## Provider Modes

Set via `MEDIA_TRANSCRIPT_PROVIDER` (default: `mock`):

| Provider   | Behavior |
|------------|----------|
| `sidecar`  | Always takes priority when a matching transcript sidecar exists next to the media file |
| `mock`     | Returns deterministic placeholder transcripts; no external dependency |
| `api`      | Calls an OpenAI-style audio transcription endpoint (`/audio/transcriptions`) |
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

To use the ASR API provider, set these environment variables **before starting the backend**:

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

**Important**: After changing environment variables, restart the backend. Media files that were already ingested must be re-ingested to use the new transcript provider.

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

Only media sources with `transcript_provider` of `sidecar` or `api` are eligible. Mock and disabled providers are skipped. If the transcript is too short, derived chunks are not generated.

## Frontend Visibility

Open **Settings → Runtime** to see the read-only **Media Transcript Provider** card. It shows:

- Status (Enabled / Disabled / Enabled — missing key)
- Provider (`api`, `mock`, `disabled`)
- API Key and Base URL configured/missing status
- Model and timeout
- Capability: **Transcript-only ASR**
- Limitations: no frame understanding, no multimodal embedding
- Config source: Environment variables

No API key is exposed. The frontend cannot edit or save media transcript credentials; configuration remains environment-variable based.

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
