# MindDock 中文说明

## 项目简介

MindDock 是一个面向毕业设计演示的本地知识库问答后端，当前实现了一套最小可演示的 RAG 流程：

- 导入本地 `.md` / `.txt` / `.pdf` 文档
- 构建本地向量知识库
- 提供 `/search`、`/chat`、`/summarize` 接口
- 支持基于文件变更的增量更新

## 架构简述

当前代码结构可以分成 4 层：

- API 层：`app/main.py`、`app/api/`
  负责提供 FastAPI 接口、校验请求和返回数据
- 服务层：`app/services/`
  负责搜索、问答、总结，以及引用信息的组织
- RAG 与存储层：`app/rag/`
  负责文档切分、向量化、Chroma 存储、全量导入和增量更新
- LLM 层：`app/llm/`
  负责选择真实模型或 `MockLLM`

核心流程如下：

```text
knowledge_base/ 文档
  -> app.rag.ingest 全量导入
  -> Chroma 向量库
  -> /search 检索
  -> /chat 问答
  -> /summarize 总结
```

如果开启 watcher，则文件变更会进入：

```text
watcher.py -> incremental.py -> vectorstore.py
```

## 当前主要改进

目前仓库已经补齐并整理了这些能力：

- 增加 `/summarize` 接口，支持基于检索结果生成带引用的总结
- `/search` 与 `/chat` 支持统一 citation 结构返回
- 增量更新支持 create / modify / delete，并补了测试与文档
- README 与演示文档已经整理为适合本地演示的流程
- 补充了 `knowledge_base/example.md`，新克隆后可以直接演示
- 增加了 `app.demo` 命令层，方便彩排与答辩现场操作

## 本地启动流程

当前推荐把 `conda` 作为默认本地环境方案，统一毕业设计演示和日常开发路径。

在项目根目录执行：

```powershell
conda env create -f environment.yml
conda activate minddock
python -m app.demo ingest
python -m app.demo serve
```

如果你已经有旧的 `.venv` 工作流，也仍然可以继续使用；但新环境准备、演示彩排和文档说明都建议优先以 conda 为准。

启动后可访问：

- `http://127.0.0.1:8000/docs`
- `http://127.0.0.1:8000/health`

## 增量更新演示

如果要演示知识库文件变更后的自动更新，再开一个终端执行：

```powershell
conda activate minddock
python -m app.demo watch
```

然后在 `knowledge_base/` 下新增、修改或删除 `.md` / `.txt` 文件即可。

## 说明

- 默认不需要额外配置 `.env`
- 没有 `LLM_API_KEY` 时，`/chat` 和 `/summarize` 会走 `MockLLM`
- 如果 `sentence-transformers` 不可用，会回退到 `DummyEmbedding`，流程仍可运行，但检索效果会变弱
- 当前推荐使用 `environment.yml` 创建 conda 环境，并通过 `python -m app.demo ...` 进行演示
- 日志固定输出到 `logs/`，默认包含：
  - `logs/minddock.info.log`
  - `logs/minddock.debug.log`
  - `logs/minddock.trace.log`
