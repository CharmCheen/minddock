# Local ASR Provider

MindDock 的 Media Transcript Provider 支持 **Local ASR** 模式，通过本地独立运行的 OpenAI-compatible ASR 伴生服务实现语音转文字。

## 设计原则

- **不修改 MindDock 主进程**：`faster-whisper` 不内嵌进 MindDock，而是运行在独立的 `local_asr_server` 中。
- **不调用外部 API**：全部计算在本地完成，不上传音频到第三方。
- **不是视频画面理解**：Local ASR 只做音频/语音转录，不做帧级理解、OCR 或多模态 embedding。
- **sidecar transcript 仍优先**：如果视频旁有 `.transcript.md` 等 sidecar，MindDock 仍优先使用 sidecar，不调用 ASR。

## 本地 ASR 服务

独立服务路径：`D:\大学\毕业设计\code\local_asr_server`

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
| Local ASR Server Path | `D:\大学\毕业设计\code\local_asr_server` | 服务目录 |
| Host | `127.0.0.1` | 监听地址 |
| Port | `9001` | 监听端口 |
| Model | `small` | faster-whisper 模型 |
| Device | `auto` | 优先 `cuda`，失败自动回退 `cpu` |
| Compute Type | `int8` | 量化类型 |
| Auto Start | `true` | MindDock 自动启动本地服务 |
| Timeout | `120` | 请求超时（秒） |

Local ASR 模式不需要填写真实 API key。后端内部使用占位 key `local-dev-key` 访问本地服务接口。

## 启动流程

1. 用户选择 `Local ASR` 并保存。
2. ingest 无 sidecar 视频时，`media_loader` 发现 `provider=local`。
3. 调用 `ensure_local_asr_if_enabled`：
   - 若 `auto_start=true` 且服务未运行，使用 `subprocess.Popen` 启动。
   - 轮询 `/health` 直到就绪。
   - 构造本地 base_url：`http://127.0.0.1:9001/v1`。
4. 使用 OpenAI-compatible 接口上传音频并获取 transcript。
5. 若启动失败，回退到 `mock` 并记录 warning。

## 环境变量

如果不想通过前端配置，也可以设置环境变量：

```bash
MEDIA_TRANSCRIPT_PROVIDER=local
MEDIA_TRANSCRIPT_LOCAL_ASR_SERVER_PATH=D:\大学\毕业设计\code\local_asr_server
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
