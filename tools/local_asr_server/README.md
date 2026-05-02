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
