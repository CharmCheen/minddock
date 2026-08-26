# MindDock 中文项目说明

MindDock 是一个面向个人知识库的本地 RAG 助手。项目重点不是做通用聊天机器人，而是把用户提供的文档、网页、图片 OCR 文本、CSV 行文本、音视频转写文本统一导入、索引、检索，并生成带有可验证引用的 grounded answer。

当前版本已经形成毕业设计答辩演示所需的主要闭环：多源导入、Chroma 向量索引、检索、问答、摘要、对比、引用溯源、Source Catalog、Source Drawer、增量同步、Workflow Trace、运行时配置、媒体转写配置和前端统一执行入口。

## 当前状态

已经完成并可演示：

- 本地 Markdown、TXT、文本型 PDF、CSV、图片、音频、视频导入。
- URL / HTML 页面导入，并提取 `og:title`、`og:description`、`og:image`、canonical、domain 等元数据。
- Chroma 持久化向量存储。
- `/search`、`/chat`、`/summarize`、`/compare`、`/ingest`、`/health` 后端接口。
- Source 生命周期管理：列表、详情、chunk 预览、删除、重建索引。
- watchdog 增量同步：新增、修改、删除、移动。
- 检索、问答、摘要、对比共用引用和证据链路。
- Prompt Profile Registry，用于 grounded chat、summary、compare 的提示词版本化。
- Source Skill 控制面，用于可信内置导入能力和本地 manifest 注册。
- 前端统一执行入口、SSE 事件流、运行状态回放和取消。
- 运行时配置面板：LLM profile、active runtime、媒体转写 provider、本地 ASR 状态和模型预加载。
- 日程候选提取：从索引文本中扫描候选事件，支持确认和忽略。
- GitHub Actions CI baseline，用于运行核心回归测试。

部分完成或带限制的能力：

- 静态网页正文抽取已经可用，但不支持 JS 渲染、登录态、付费墙和通用爬虫。
- CSV 以 rows-as-text 方式进入知识库，不是表格推理引擎。
- 图片能力是 OCR 文本导入，不是图片 caption、多模态 embedding 或图像理解。
- 音视频能力基于转写文本，可来自 sidecar、远程 OpenAI-style transcription API 或本地 ASR；不是原生音视频理解。
- rerank 是启发式 rerank，不是训练型 cross-encoder。
- compression 是 trimming / lexical compression，不是 LLM context compression。
- 日程提取目前生成 reviewable candidates，还没有生产级日历同步。
- LangGraph 用于检索准备子流程，还不是完整 Agent 控制器。

未来工作：

- Word / Docx 导入。
- 完整 Skill Market、远程插件安装、签名校验和沙箱执行。
- OpenAPI / MCP tool import。
- 长期用户记忆和自动用户画像。
- 真正的 cross-encoder reranker 和 LLM context compression。
- 生产级 calendar sync。
- 完整 LangGraph Agent controller。

## 技术架构

- Backend: FastAPI
- Frontend: React + Vite + TypeScript
- Vector Store: Chroma
- RAG Pipeline: loader -> parser/chunker -> embedding -> vectorstore -> retrieval -> rerank -> evidence window -> generation -> citation
- Runtime: runtime port/adapter + active config，支持 mock 和真实 LLM provider
- Evaluation: 本地 benchmark runner 和 CI baseline
- CI: `.github/workflows/ci-baseline.yml`

关键模块：

- `app/rag/`: source loader、PDF parser、structured chunker、vectorstore、retrieval、watcher。
- `app/services/`: search/chat/summarize/compare/ingest/catalog 等用例服务。
- `app/api/`: HTTP route、schema、presenter、streaming。
- `app/application/`: 前端统一 facade、orchestrator、run control、client events。
- `app/runtime/`: LLM runtime、媒体转写 active config、本地 ASR bootstrap。
- `app/skills/`: Source Skill manifest、registry、policy、trusted handlers。
- `app/schedule/`: 日程候选抽取、模型和本地存储。
- `frontend/`: 前端页面和交互体验。
- `docs/`: 架构、模型、演示、测试、论文图表等文档。
- `tests/`: unit / integration / contract tests。

## 支持的知识源

`source_type` 目前包括：

- `file`
- `url`

内置文件与输入能力：

- Markdown 和 TXT：作为主要文本源。
- PDF：支持文本型 PDF，并尽量保留 page、section、block metadata。
- URL / HTML：支持可直接 fetch 的静态 HTML 页面。
- CSV：按行转成文本进入 RAG。
- 图片：支持 `.png`、`.jpg`、`.jpeg`、`.webp`，可使用 mock、disabled 或 RapidOCR；长图会先纵向切片再 OCR。
- 音频：支持 `.mp3`、`.wav`、`.m4a`、`.aac`、`.flac`、`.ogg`、`.webm`。
- 视频：支持 `.mp4`、`.mov`、`.mkv`、`.webm`、`.avi`。
- 音视频转写 sidecar：支持 `.transcript.md`、`.transcript.txt`、`.srt`、`.vtt`。

重要规则：

- `source` 是过滤和引用中的稳定身份。
- 本地文件的 `source` 是相对知识库目录的路径。
- URL 的 `source` 是重定向后的最终 URL。
- `doc_id` 根据 `source` 确定性生成。

## 快速开始

创建并进入环境：

```powershell
conda env create -f environment.yml
conda activate minddock
```

安装项目：

```powershell
pip install -e ".[dev]"
```

构建索引：

```powershell
python -m app.demo ingest
```

追加 URL：

```powershell
python -m app.demo ingest --no-rebuild --url http://example.com
```

启动后端：

```powershell
python -m app.demo serve
```

启动前端：

```powershell
cd frontend
npm install
npm run dev
```

访问：

```text
Backend API: http://127.0.0.1:8000
API Docs:    http://127.0.0.1:8000/docs
Frontend:    http://localhost:5173
```

常用 CLI：

```powershell
python -m app.demo search --query "local Chroma"
python -m app.demo chat --query "How is data stored?"
python -m app.demo summarize --topic "storage design"
python -m app.demo compare --question "Compare the storage approaches across documents"
python -m app.demo sources
python -m app.demo source-chunks --source notes.md --limit 5 --offset 0
python -m app.demo watch --once
python -m app.demo evaluate
```

## 主要 API

基础能力：

- `GET /`
- `GET /health`
- `POST /ingest`
- `POST /search`
- `POST /chat`
- `POST /summarize`
- `POST /compare`

Source 生命周期：

- `GET /sources`
- `GET /sources/{doc_id}`
- `GET /sources/{doc_id}/chunks`
- `GET /sources/by-source?source=...`
- `GET /sources/by-source/chunks?source=...`
- `DELETE /sources/{doc_id}`
- `DELETE /sources/by-source?source=...`
- `POST /sources/{doc_id}/reingest`
- `POST /sources/by-source/reingest?source=...`

前端统一执行与 run control：

- `POST /frontend/execute`
- `POST /frontend/execute/stream`
- `GET /frontend/runs/{run_id}`
- `GET /frontend/runs/{run_id}/events`
- `POST /frontend/runs/{run_id}/cancel`

运行时与媒体转写配置：

- `GET /frontend/runtime-profiles`
- `GET /frontend/runtime-config`
- `PUT /frontend/runtime-config`
- `POST /frontend/runtime-config/test`
- `POST /frontend/runtime-config/reset`
- `GET /frontend/media-transcript-config`
- `PUT /frontend/media-transcript-config`
- `POST /frontend/media-transcript-config/test`
- `POST /frontend/media-transcript-config/reset`
- `GET /frontend/media-transcript-config/local/status`
- `POST /frontend/media-transcript-config/local/start`
- `GET /frontend/media-transcript-config/local/model/status`
- `POST /frontend/media-transcript-config/local/model/preload`

可验证文献工作台（PRD v1.2）：

- `GET /frontend/traces` — 归档 run trace 列表（重启后仍可查，含失败/取消 run）
- `GET /frontend/traces/{run_id}` — 读取单个归档 trace（含引用自检报告）
- `POST /frontend/citations/export` — BibTeX / GB/T 7714 / APA 引用导出
- `POST /frontend/review-workbench` — 多源综述工作台（review.v1 对比表 + 可点击引用）

chat/summarize/compare 的统一执行响应中，text artifact metadata 新增
`evidence_badge`（green/yellow/red/unknown 证据充分度，确定性映射）与
`citation_self_check`（逐条引用三态自检报告）；检索过滤新增
`authors` / `year_from` / `year_to` 学术元数据过滤。

MCP 只读 POC：

```powershell
# 后端运行中，另开终端：
python tools/minddock_mcp_server.py
```

在支持 MCP 的客户端（Claude Desktop / Cursor）中把该命令配置为 stdio
server，即可调用 `minddock_search` 工具查询本地知识库。

Source Skill 和日程候选：

- `GET /frontend/skills`
- `GET /frontend/skills/{skill_id}`
- `GET /frontend/source-skills`
- `GET /frontend/source-skills/{skill_id}`
- `POST /frontend/source-skills/validate`
- `POST /frontend/source-skills/register`
- `POST /frontend/source-skills/{skill_id}/enable`
- `POST /frontend/source-skills/{skill_id}/disable`
- `GET /frontend/schedule-candidates`
- `POST /frontend/schedule-candidates/scan`
- `POST /frontend/schedule-candidates/{candidate_id}/confirm`
- `POST /frontend/schedule-candidates/{candidate_id}/dismiss`
- `POST /frontend/skills/schedule-extraction/run`

## 检索过滤语义

`/search`、`/chat`、`/summarize`、`/compare` 共用同一套 retrieval/filter model。

支持：

- `source`: 单值或多值。
- `source_type`: 单值或多值。
- `section`: 精确匹配。
- `title_contains`: 受控的大小写不敏感 contains。
- `requested_url_contains`: 受控的大小写不敏感 contains。
- `page_from` / `page_to`: 页码范围。

当前限制：

- 不是通用 boolean DSL。
- `contains` 只开放给少数字段。
- 不支持复杂嵌套过滤表达式。

## 答辩演示建议

最短演示路径：

1. 启动后端：`python -m app.demo serve`。
2. 启动前端：在 `frontend` 目录运行 `npm run dev`。
3. 打开 Source 列表，展示已索引来源。
4. 导入或放入本地知识库文档，运行 ingest 或 `watch --once`。
5. 执行 chat、summarize、compare。
6. 展示 citation、source/page/chunk 引用、evidence preview 和 workflow trace。
7. 展示 Prompt Profile、Source Skill、User Preference、Runtime Config 和 Media Transcript Config。

更多脚本见：

- `RUN.md`
- `docs/demo-guide.md`
- `docs/DEMO_SCRIPT.md`
- `docs/FINAL_DEMO_SCRIPT.md`
- `docs/thesis-alignment.md`

## 测试

运行完整测试：

```powershell
python -m pytest
```

运行 CI baseline：

```powershell
python scripts/run_ci_baseline.py
```

运行重点单元和集成测试：

```powershell
python -m pytest tests/unit/test_retrieval_models.py tests/unit/test_search_service.py tests/unit/test_chat_service.py tests/unit/test_summarize_service.py tests/integration/test_system_pipeline.py
```

前端构建：

```powershell
cd frontend
npm run build
```

前端 smoke test：

```powershell
cd frontend
npm run test:smoke
```

## 已知限制

- URL 抽取依赖可 fetch 的 HTML 页面，不支持 JS 渲染页面、登录态、付费墙或通用爬虫。
- 过滤语义是受控能力，不是完整查询语言。
- enhanced filters 可能让 vector store 多取候选，再由 retrieval 层后过滤。
- rerank 是启发式方法，不是训练型 cross-encoder。
- compression 是裁剪和词法压缩，不是 LLM compression。
- Source Skill 是可信内置控制面，不是完整 Skill Market。
- 用户偏好是 workspace-local 请求默认值，不是长期记忆或自动画像。
- Chroma rebuild 在 Windows 上已有缓解，但仍不完全由应用层控制。
- CI 当前是 baseline regression suite，不是完整生产发布流水线。

## License

MIT
