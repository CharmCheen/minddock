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

## 智能体（Agent）架构

### 整体架构

MindDock 基于 LangGraph 构建智能体工作流，采用"检索 → 推理 → 生成"三阶段设计：

1. **检索阶段（Retrieval）**：向量相似度召回 + metadata-aware rerank
2. **推理阶段（Reasoning）**：基于 LangChain Chain 实现意图识别、任务分解
3. **生成阶段（Generation）**：引用驱动的 grounded generation，强制输出引用链

### 工作流类型

| 工作流 | 描述 |
|--------|------|
| `retrieval` | 向量检索 → rerank → 证据组装 → 生成 |
| `compare` | 查询分解 → 双路检索 → topic diversity merge → 对比生成 |
| `summarize` | 检索 → map-reduce → 结构化输出 |

### 关键实现

- 入口：`app/application/orchestrators.py`（ChatOrchestrator）
- 工作流定义：`app/workflows/langgraph_pipeline.py`（RetrievalWorkflow）
- 服务编排：`app/services/chat_service.py`、`app/services/compare_service.py`
- 智能体注册：`app/skills/`（SkillRegistry）

### 意图识别流程

用户输入 → 轻量级意图分类 → TaskType（search/chat/compare/summarize/structured_output）→ 对应 Orchestrator 方法 → 执行 DAG 工作流
