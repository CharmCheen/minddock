# MindDock 中文项目说明

MindDock 是一个面向个人知识库的可验证 RAG 系统，支持多源知识接入、持续同步、引用溯源和工作流可观测。项目目标不是做通用聊天机器人，而是把用户提供的文档解析、索引、检索，并生成带可验证引用的 grounded answer。

当前版本已经形成毕业设计演示所需的主体闭环：PDF 结构化解析、多源导入、向量索引、检索、问答、摘要、对比、citation 展示、source catalog、source drawer、持续同步和 workflow trace。

## 核心功能

- **文档导入**：支持本地文件和 URL 导入。
- **文件格式**：支持 PDF、Markdown、TXT、CSV，以及网页 URL 正文抽取、Image OCR。
- **多源接入**：通过 Source Skill Contract 规范化异构数据源；已实现 `url.extract`、`image.ocr`、`csv.extract`，未来可扩展 audio/video/image caption skill。
- **向量索引**：使用 Chroma 持久化存储 chunk、embedding 和 metadata。
- **检索**：提供 `/search` 接口，返回带 source/citation 的检索结果。
- **问答**：提供 `/chat` 接口，基于检索证据生成 grounded answer。
- **摘要**：提供 `/summarize`，复用同一检索和引用链路。
- **对比**：提供 `/compare`，支持多文档 grounded comparison。
- **引用**：citation 包含 hit chunk、evidence window、页码、section、block type 等可验证字段。
- **Source 管理**：支持 source 列表、详情、chunk inspect、删除和重新入库。
- **前端展示**：提供 chat、citation list、source drawer、runtime settings 和 source scope 状态。
- **持续同步**：watchdog `watch --once` 支持基于内容哈希的增量增删改。
- **工作流可观测**：workflow trace 展示 retrieval / rerank / source cap / evidence window 等结构化 metadata。

## 技术架构

- **Backend**：FastAPI。
- **Vector Store**：Chroma。
- **RAG Pipeline**：loader -> parser/chunker -> embedding -> vectorstore -> retrieval -> rerank -> evidence window -> generation -> citation。
- **PDF 处理**：包含 structured chunking，尽量保留 page、section、block type 等 metadata。
- **Evidence Window**：检索仍使用小 chunk，回答和引用阶段扩展为更完整的 evidence window，保证 `hit_chunk_id in window_chunk_ids`。
- **Citation Metadata**：后端和前端共同展示 `citation_label`、`evidence_preview`、`hit_in_window`、`window_chunk_count` 等字段。
- **Source Skill Contract**：将 PDF、Markdown、TXT、URL、Image OCR、CSV 等知识源统一描述为 source extraction skills，输出统一的 `SourceLoadResult`。
- **Frontend Facade / Runtime Adapter**：前端统一调用应用层 facade，后端 runtime 可切换 mock 或真实 LLM provider。

## 技术亮点

### 1. Structured PDF Chunking

系统在 PDF 入库时尽量保留标题、段落、页码、section、caption/table/list 等结构信息，为后续检索和引用提供 metadata 支撑。

### 2. Retrieval Unit 与 Answer/Citation Unit 分层

传统做法容易把“命中块”直接当作“回答块”和“引用块”。MindDock 将检索粒度和回答/引用粒度分开：检索时保持小 chunk 提升精度，回答和引用时通过 evidence window 补足上下文。

### 3. Hit-preserving Evidence Window

Evidence window 保证 `hit_chunk_id in window_chunk_ids`，避免扩窗、合并、裁剪后丢失真正命中的 chunk。这样 citation 变长后仍然可追溯。

### 4. Verifiable Citation Metadata

Citation 不只返回短 snippet，还包含：

- `hit_chunk_id`
- `window_chunk_ids`
- `hit_in_window`
- `window_chunk_count`
- `citation_label`
- `evidence_preview`
- `page_start` / `page_end`
- `section_title`
- `block_types`

这些字段让用户和前端都能判断答案来源是否可信。

### 5. Section-aware Rerank

对于明确提到 section 的 query，系统会对匹配 `section_title` 的候选做轻量加权。例如 `SYSTEM DESIGN section` 能稳定优先命中 `SYSTEM DESIGN · p.3`。

### 6. Local-doc Source Priority

当 query 明确说 `local docs`、`local documents` 或“本地文档”时，系统优先保留本地 Markdown 文档，减少无关论文 PDF 混入。

### 7. Structured-ref Lexical Injection

对于 `Table 1`、`Figure 14`、`Fig. 2`、`表1`、`图2` 这类结构编号 query，系统会窄触发 BM25 lexical candidates，并用 `chunk_id` 回查真实 `RetrievedChunk` 后注入 rerank 候选池。

### 8. Source Consistency Cap

在高置信单源场景下，系统会减少低位 unrelated source citation。例如 `Table 1 of the Milvus paper` 的最终 citations 会优先保持在 Milvus PDF 内。

### 9. Source Skill Contract

MindDock 通过 Source Skill Contract 将 URL extraction、Image OCR、CSV rows-as-text 等异构数据源统一接入 RAG pipeline。新增 source skill 只需实现 extraction 层，无需修改 retrieval、rerank、citation 或 frontend。

### 10. Experience-oriented Validation

本阶段采用真实体验 query 验收，重点观察 citation 是否可验证、source 是否一致、answer 是否被正确证据支撑。它不是大规模 benchmark。

## 当前局限

- Figure/table object-level parsing 仍不完整，尚未建立完整的图表对象级 metadata。
- Cross-page evidence 仍有局限，跨页段落、图表数字和 layout cleaning 仍需进一步增强。
- Rerank 为 heuristic rerank，不是学习型 cross-encoder reranker。
- Context compression 主要是 trimming / lexical compression，不是 LLM compression。
- URL source 仅支持 static HTML，不支持 JavaScript 渲染、登录态、反爬。
- Image OCR 提供 OCR text 路径，不支持 image caption、PDF figure extraction、multimodal embedding。
- CSV source skill 将行转换为文本，不支持 Excel、SQL、表格推理引擎。
- 当前 validation 是 small experience-oriented validation，不是大规模定量 benchmark。

## 目录结构概览

```text
app/              后端 FastAPI、RAG、服务层、API schema
frontend/         React + Vite 前端
docs/             架构文档、演示脚本、验收报告
tests/            unit / integration / contract tests
eval/             小规模评测数据和 chunking 评估材料
knowledge_base/   演示知识库文档，包括 PDF 和 Markdown
data/chroma/      本地 Chroma 持久化索引
```

## 快速开始

详细运行步骤见 [RUN.md](RUN.md)。

最常用本地演示路径：

```powershell
conda activate minddock
python -m app.demo serve
```

另开一个终端启动前端：

```powershell
cd frontend
npm install
npm run dev
```

打开：

```text
Backend API: http://127.0.0.1:8000
API Docs:    http://127.0.0.1:8000/docs
Frontend:    http://localhost:5173
```

## 核心 Demo 建议

答辩推荐按以下顺序演示：

1. **H1: Section-aware Rerank** — `What does the SYSTEM DESIGN section of the Milvus paper describe?`
2. **N2: Local-doc Source Priority** — `What are the main steps in the RAG pipeline according to the local docs?`
3. **Watchdog sync-once** — 新增 Markdown 文件后 `watch --once`，验证增量同步
4. **Source Drawer / Citation** — 展示 source、page、section label、chunk preview
5. **Workflow Trace** — 展示 `--trace` 背后的 retrieval / rerank / evidence window metadata

详细脚本见 [docs/FINAL_DEMO_SCRIPT.md](docs/FINAL_DEMO_SCRIPT.md)。
