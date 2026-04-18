# LLM 平台配置说明

## 概述

MindDock 后端通过兼容 OpenAI 接口标准的适配器调用大语言模型，支持任意提供 OpenAI-compatible API 的 LLM 平台。配置通过环境变量或 `app/core/config.py` 中的 `Settings` 类管理。

---

## 支持的 LLM 平台

| 平台 | Provider 值 | 默认模型 | 说明 |
|------|------------|---------|------|
| OpenAI | `openai` | `gpt-4o-mini` | 需要 API Key |
| DeepSeek | `deepseek` | `deepseek-chat` | 需要 API Key，base_url 需替换 |
| MiniMax | `minimax` | `MiniMax-Text-01` | 需要 API Key |
| Ollama（本地） | `ollama` | `llama3` | 无需 API Key，本地运行 |

---

## 配置项说明

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `LLM_API_KEY` | API 密钥 | `""` |
| `LLM_PROVIDER` | 提供商名称 | `openai` |
| `LLM_BASE_URL` | API 端点 | `https://api.openai.com/v1` |
| `LLM_MODEL` | 模型名称 | `gpt-4o-mini` |
| `LLM_TIMEOUT_SECONDS` | 请求超时（秒） | `30.0` |

---

## 配置示例

### OpenAI（默认）

```bash
# .env 或环境变量
LLM_API_KEY=sk-xxxxx
LLM_PROVIDER=openai
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
```

### DeepSeek

```bash
LLM_API_KEY=sk-xxxxx
LLM_PROVIDER=deepseek
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
```

### MiniMax

```bash
LLM_API_KEY=xxxxx
LLM_PROVIDER=minimax
LLM_BASE_URL=https://api.minimax.chat/v1
LLM_MODEL=MiniMax-Text-01
```

### Ollama（本地离线）

```bash
LLM_API_KEY=不需要
LLM_PROVIDER=ollama
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL=llama3
```

> 注意：Ollama 需要提前在本地安装并启动。安装方式：`ollama pull llama3` 然后 `ollama serve`。

---

## 实现位置

- LLM 适配器入口：`app/llm/openai_compatible.py`
- 配置定义：`app/core/config.py`（`Settings` 类）
- 运行时工厂：`app/llm/factory.py`（根据 `llm_provider` 选择具体适配器）

---

## 当前实现状态

- ✅ `OpenAICompatibleLLM`：支持任意 OpenAI-compatible API 端点
- ✅ `MockLLM`：纯本地 mock 实现，用于无 API Key 时的基础功能演示
- ⚠️ DeepSeek/MiniMax/Ollama 专用适配器：当前通过 `OpenAICompatibleLLM` + 切换 base_url 实现，暂不需要独立适配器类
