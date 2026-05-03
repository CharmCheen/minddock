# Local ASR Provider

## One-click Local Demo Startup

Use `start.bat` from the repository root for the local demo startup path. It
checks the `minddock` and `local-asr` conda environments, verifies that
`faster_whisper` imports in `local-asr`, verifies the local
`models/faster-whisper-base` directory, starts Local ASR, starts the backend,
saves the Local ASR provider config, triggers model preload, waits until the
model status is `ready`, starts the incremental `knowledge_base` watcher,
starts the frontend dev server, verifies that the frontend dev server can
proxy backend API calls, and opens the browser.

`start.bat` brings the system to a usable Ready state and starts automatic
incremental ingestion. It does not run rebuild ingest and does not clear
Chroma. Preload Model loads the configured faster-whisper model only; Local
ASR transcription is triggered only when the watcher or manual ingest needs to
index a media file without a sidecar transcript.

Use `run_demo_ingest.bat` after `start.bat` reports Ready. It checks backend
health, Local ASR health, and model readiness, then asks for confirmation
before running `python -m app.demo ingest`. Because demo ingest is a rebuild
ingest, it recreates Chroma. If the backend is still running, it may hold
`data/chroma/chroma.sqlite3` open. Close the `MindDock-Backend` window, or
release port `8000` when the script asks, before continuing.

For normal daily demo use, do not run rebuild ingest. Drop new or changed files
into `knowledge_base`; the watcher started by `start.bat` runs an initial
non-rebuild sync and then keeps watching for create/modify/delete events.

For the first real smoke test, prefer a valid English-name `.wav` file without
a same-name sidecar transcript, for example
`knowledge_base/local_asr_smoke.wav`. Try `.mp3` next and `.mp4` only after
audio smoke passes. Avoid very short, silent, damaged `.mp4` files and avoid
Chinese filenames for the first smoke test.

Recommended recording content:

```text
这是 MindDock 本地语音识别测试，系统应该把这段录音转录成文本并入库。
```

Model weights are not committed to git. Keep `models/` untracked and place the
base model files under:

```text
models/faster-whisper-base/
  model.bin
  config.json
  tokenizer.json
  vocabulary.txt
```

MindDock 的 Media Transcript Provider 支持 **Local ASR** 模式，通过本地独立运行的 OpenAI-compatible ASR 伴生服务实现语音转文字。

## 设计原则

- **不修改 MindDock 主进程**：`faster-whisper` 不内嵌进 MindDock，而是运行在独立的 `local_asr_server` 中。
- **不调用外部 API**：全部计算在本地完成，不上传音频到第三方。
- **不是视频画面理解**：Local ASR 只做音频/语音转录，不做帧级理解、OCR 或多模态 embedding。
- **sidecar transcript 仍优先**：如果视频旁有 `.transcript.md` 等 sidecar，MindDock 仍优先使用 sidecar，不调用 ASR。

## 本地 ASR 服务

独立服务路径：`D:\大学\毕业设计\code\V0.1\tools\local_asr_server`

Local ASR companion server is included under `tools/local_asr_server`.
It should be installed in a separate environment, for example `local-asr`.
It is not part of MindDock's main Python dependencies.
It does not run unless the user selects Local ASR and starts it.
First model preload may download faster-whisper model files into the user's HuggingFace cache.

接口兼容 OpenAI：

- `GET /health`
- `POST /v1/audio/transcriptions`

依赖 `faster-whisper`，默认模型建议 `small int8`。

## 硬件建议

| 显存 | 建议模型 |
|------|----------|
| 4GB (RTX 3050 Laptop) | `small` 或 `base`，`int8` |
| 8GB+ | `small` / `medium`，`int8` |

首次启动会自动下载模型到 `~/.cache/huggingface`，耗时取决于网络。

## 前端配置

打开 **Settings → Runtime → Media Transcript Provider**：

| 字段 | 默认值 | 说明 |
|------|--------|------|
| Provider | `Mock` | 选择 `Local ASR` |
| Local ASR Server Path | `D:\大学\毕业设计\code\V0.1\tools\local_asr_server` | 服务目录 |
| Host | `127.0.0.1` | 监听地址 |
| Port | `9001` | 监听端口 |
| Model | `small` | faster-whisper 模型 |
| Device | `auto` | 优先 `cuda`，失败自动回退 `cpu` |
| Compute Type | `int8` | 量化类型 |
| Auto Start | `true` | MindDock 自动启动本地服务 |
| Timeout | `120` | 请求超时（秒） |

Local ASR 模式不需要填写真实 API key。后端内部使用占位 key `local-dev-key` 访问本地服务接口。

## 推荐操作流程

```text
Start Local ASR → Check Status → Preload Model → Ready → ingest
```

1. **选择 `Local ASR` 并 Save** — 保存配置到 `data/active_media_transcript.json`。
2. **Start Local ASR** — 启动本地 ASR 服务进程（若已运行则显示 Already Running）。
3. **Check Status** — 检查服务是否响应 `/health`。
4. **Preload Model** — 触发后台模型加载。首次会下载 faster-whisper 模型到 `~/.cache/huggingface`。
5. **Wait until Ready** — 通过 Check Model 查看模型状态变为 `ready`。
6. **Run ingest** — 上传视频/音频，MindDock 调用 `/v1/audio/transcriptions` 转录。

**注意**：Preload Model 只加载模型，不转录。Check Status / Check Model 也不转录。只有 ingest 才会真实转录。

## 启动与模型加载

### local_asr_server 接口

- `GET /health` — 服务健康检查
- `GET /v1/models/status?model=small&device=auto&compute_type=int8` — 查询模型加载状态
- `POST /v1/models/preload` — 后台触发模型预加载
- `POST /v1/audio/transcriptions` — OpenAI-compatible 转录（需模型已 ready）

### 模型状态

| 状态 | 含义 |
|------|------|
| `not_loaded` | 模型尚未加载 |
| `loading` | 正在后台加载（首次可能下载） |
| `ready` | 模型已加载，可以转录 |
| `failed` | 加载失败 |

### ingest 流程

ingest 无 sidecar 视频时，`media_loader` 发现 `provider=local`：

1. 调用 `ensure_local_asr_if_enabled`：
   - 若 `auto_start=true` 且服务未运行，使用 `subprocess.Popen` 启动。
   - 轮询 `/health` 直到就绪。
   - 构造本地 base_url：`http://127.0.0.1:9001/v1`。
2. 使用 OpenAI-compatible 接口上传音频并获取 transcript。
3. 若启动失败，回退到 `mock` 并记录 warning。

## 环境变量

如果不想通过前端配置，也可以设置环境变量：

```bash
MEDIA_TRANSCRIPT_PROVIDER=local
MEDIA_TRANSCRIPT_LOCAL_ASR_SERVER_PATH=D:\大学\毕业设计\code\V0.1\tools\local_asr_server
MEDIA_TRANSCRIPT_LOCAL_ASR_HOST=127.0.0.1
MEDIA_TRANSCRIPT_LOCAL_ASR_PORT=9001
MEDIA_TRANSCRIPT_LOCAL_ASR_MODEL=small
MEDIA_TRANSCRIPT_LOCAL_ASR_DEVICE=auto
MEDIA_TRANSCRIPT_LOCAL_ASR_COMPUTE_TYPE=int8
MEDIA_TRANSCRIPT_LOCAL_ASR_AUTO_START=true
MEDIA_TRANSCRIPT_LOCAL_ASR_TIMEOUT_SECONDS=120
```

## 测试

```bash
# Bootstrap 单元测试
python -m pytest tests/unit/test_local_asr_bootstrap.py -x --tb=short

# media_loader 单元测试
python -m pytest tests/unit/test_media_loader.py -x --tb=short

# 配置 API 集成测试
python -m pytest tests/integration/test_media_transcript_config_api.py -x --tb=short
```

测试中不会真实启动 `local_asr_server`，所有 health check 和 subprocess 均被 mock。

## 限制与风险

- **首次模型下载慢**：依赖 HuggingFace 缓存，首次需下载 ~500MB（small）。
- **显存限制**：4GB 显存只能用 `small` 或 `base`；`medium` 可能 OOM。
- **Auto Start 依赖 conda**：默认启动命令使用 `conda run -n local-asr`，需预先创建环境并安装依赖。
- **Test Config 不转录**：前端 "Test Config" 只检查配置完整性，不会真实上传文件做 ASR。
## Demo Startup Runbook

Use two Python environments:

- `minddock`: MindDock backend, RAG, Chroma, `python -m app.demo serve`, and `python -m app.demo ingest`.
- `local-asr`: the companion server under `tools/local_asr_server`, including `faster-whisper`, `ctranslate2`, and `uvicorn`.

Install the Local ASR environment with:

```bash
conda create -n local-asr python=3.10 -y
conda activate local-asr
pip install -r tools/local_asr_server/requirements.txt
```

`start.bat` is the demo startup script. It does:

1. Start Local ASR.
2. Start the MindDock backend.
3. Save the Local ASR provider config.
4. Preload the configured model.
5. Start the frontend.

`start.bat` does not:

- Run ingest.
- Call `/v1/audio/transcriptions`.
- Perform real transcription.
- Verify search, chat, or citations.

After `start.bat` reaches Model Ready, the watcher is also running. It uses the
existing `python -m app.demo watch` path, performs a startup non-rebuild sync,
then watches `knowledge_base` for new, modified, moved, or deleted files. Use
`run_demo_ingest.bat` only when you intentionally want the manual rebuild
workflow. That script checks backend health, Local ASR health, and model
readiness before running `python -m app.demo ingest`. It then warns that
rebuild ingest recreates Chroma and asks you to close the backend first. If
port `8000` is still occupied, the script stops instead of running ingest.

## Local Model Directory

To avoid accidental online model download during a demo, configure a local
model directory before starting Local ASR:

```bat
set LOCAL_ASR_MODEL_BASE_PATH=D:\models\faster-whisper-base
```

Supported overrides:

- `LOCAL_ASR_MODEL_BASE_PATH` for `model=base`
- `LOCAL_ASR_MODEL_SMALL_PATH` for `model=small`
- `LOCAL_ASR_MODEL_MEDIUM_PATH` for `model=medium`

If the configured path exists, `local_asr_server` uses it for both preload and
transcription. If the path is invalid, the server reports the invalid path and
falls back to the model name; that fallback may use the normal HuggingFace
resolution behavior.

## Failure Semantics

For `provider=local`, MindDock no longer falls back to mock transcripts on ASR
failure. Local ASR failures produce an empty transcript with `local_asr_*`
warnings so the demo does not index fake placeholder text.

For `provider=mock`, mock transcripts are still explicit and intentional. For
`provider=api`, the existing remote API mock fallback behavior is preserved.

## Smoke Test Advice

Use a valid English-name `.wav` file for the first real ASR smoke test, such
as `knowledge_base/local_asr_smoke.wav`. `.mp3` is the next best option. Try
`.mp4` only after audio smoke passes, and avoid very short, silent, damaged
media files or Chinese filenames for the first smoke test. Local ASR is
transcript-only: it does not do video frame understanding, OCR, frame
extraction, multimodal embedding, or LLM summary.

Demo ingest uses rebuild mode and recreates Chroma. If the backend is running,
Windows may keep `data/chroma/chroma.sqlite3` locked. Close the backend window
or release port `8000` before running `run_demo_ingest.bat`; the script prints
`netstat -ano | findstr :8000` and `taskkill /PID <pid> /F` as manual
diagnostic commands, but it does not kill processes automatically.
