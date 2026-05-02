# Local ASR Server

Standalone local ASR service for MindDock, powered by [faster-whisper](https://github.com/SYSTRAN/faster-whisper).

This server runs **outside** the MindDock main process and provides an OpenAI-compatible `/v1/audio/transcriptions` endpoint.

## Endpoints

### Health

```bash
curl http://127.0.0.1:9001/health
```

### Model Status

Check whether a model is loaded, loading, not loaded, or failed.

```bash
curl "http://127.0.0.1:9001/v1/models/status?model=small&device=auto&compute_type=int8"
```

Response:

```json
{
  "status": "ready",
  "model": "small",
  "requested_device": "auto",
  "actual_device": "cuda",
  "compute_type": "int8",
  "message": "Model is loaded and ready."
}
```

Status values: `not_loaded`, `loading`, `ready`, `failed`.

### Model Preload

Trigger background model loading. First preload may download the model from HuggingFace.

```bash
curl -X POST "http://127.0.0.1:9001/v1/models/preload" \
  -H "Content-Type: application/json" \
  -d '{"model":"small","device":"auto","compute_type":"int8"}'
```

If already `ready`, returns `ready` immediately.  
If currently `loading`, returns `loading` immediately.  
Otherwise starts a background thread and returns `loading`.

### Transcription

OpenAI-compatible audio transcription.

```bash
curl -X POST "http://127.0.0.1:9001/v1/audio/transcriptions" \
  -H "Authorization: Bearer local-dev-key" \
  -F file="@audio.mp3" \
  -F model="small"
```

Requires the model to be preloaded first.

## Device Strategy

- `device=auto`: tries `cuda` first, falls back to `cpu`.
- `compute_type=int8`: recommended for 4GB VRAM (e.g. RTX 3050 Laptop).

## Recommended Models

| GPU VRAM | Model | Compute Type |
|----------|-------|--------------|
| 4 GB     | small / base | int8 |
| 8 GB     | medium | int8 |
| 16 GB+   | large-v2 | float16 |

## Recommended Flow

1. Start the Local ASR server (MindDock Settings → Start Local ASR)
2. Check Status (ensure server is running)
3. Preload Model (select model, device, compute type)
4. Wait until Ready
5. Run ingest (MindDock will transcribe audio/video)

**Note:** Preload Model only loads the model into memory. It does **not** perform transcription, video frame understanding, OCR, or embedding.

## Run

```bash
conda run -n local-asr uvicorn server:app --host 127.0.0.1 --port 9001
```

## Requirements

- Python 3.10+
- faster-whisper
- fastapi
- uvicorn

Install the companion server in its own environment:

```bash
conda create -n local-asr python=3.10 -y
conda activate local-asr
pip install -r tools/local_asr_server/requirements.txt
```

Do not install `faster-whisper` into the main `minddock` environment unless
you are intentionally changing the architecture. MindDock talks to this server
over localhost.

## Local Model Path Overrides

By default, `faster-whisper` resolves model names such as `base`, `small`, and
`medium` normally. The first preload may download model files into the user's
HuggingFace cache.

To force a local model directory and avoid accidental online download, set one
of these variables before starting the server:

```bat
set LOCAL_ASR_MODEL_BASE_PATH=D:\models\faster-whisper-base
set LOCAL_ASR_MODEL_SMALL_PATH=D:\models\faster-whisper-small
set LOCAL_ASR_MODEL_MEDIUM_PATH=D:\models\faster-whisper-medium
```

Mapping:

- `model=base` -> `LOCAL_ASR_MODEL_BASE_PATH`
- `model=small` -> `LOCAL_ASR_MODEL_SMALL_PATH`
- `model=medium` -> `LOCAL_ASR_MODEL_MEDIUM_PATH`

If the configured directory exists, preload and transcription both use that
local path and return `resolved_model` / `model_path` in status responses. If
the configured directory is invalid, the server does not create it and reports
the invalid path in the response message.

## Demo Workflow Boundary

`start.bat` may start this server and preload a model, but it does not ingest
media and does not call `/v1/audio/transcriptions`. Real transcription happens
only when MindDock ingest runs.

For a first smoke test, prefer a valid `.wav` or `.mp3` file. Try `.mp4` only
after audio smoke passes. This server transcribes audio; it does not perform
video frame understanding, OCR, frame extraction, multimodal embedding, or LLM
summary.
