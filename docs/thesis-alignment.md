# 论文口径与实际实现对齐说明

> 本文档供论文撰写和答辩准备参考，确保论文描述与代码实际实现一致。

---

## 1. Rerank / 重排

### 实际实现
`app/rag/postprocess.py` 中的 `HeuristicReranker`：
- 结合余弦相似度距离（distance）加权 45%
- 词汇重叠得分（lexical overlap）加权 40%
- 元数据字段匹配加权 10%
- 短文本奖励（bonus）加权 5%
- **非** 学习型重排模型（如 bge-reranker）

### 论文推荐表述

**安全写法（推荐）**：
> "系统在检索后阶段引入轻量级重排策略，综合语义距离与词汇重叠程度对候选片段进行排序，以提升 top-k 命中率。"

**避免的写法**：
> ~~"系统使用 bge-reranker 重排模型进行候选重排序"~~
> ~~"采用基于交叉编码器的重排方法"~~

**如果要保留"重排"这个亮点**，可以在论文中注明：
> "当前实现为启发式重排（lexical overlap + cosine distance 加权），后续可替换为学习型交叉编码器模型以进一步提升精度。"

---

## 2. Context Compression / 上下文压缩

### 实际实现
`app/rag/postprocess.py` 中的 `TrimmingCompressor`：
- 对每个 hit，最多保留 2 个句子
- 每个句子最多 280 字符
- 最多处理 4 个 hit
- 基于词汇重叠打分选择最重要的句子
- **非** 基于 LLM 的摘要式压缩

### 论文推荐表述

**安全写法**：
> "系统对候选上下文进行裁剪压缩，保留与 query 词汇重叠度最高的句子，兼顾信息密度与 prompt 长度限制。"

**避免的写法**：
> ~~"使用 LLM 对检索上下文进行摘要压缩"~~
> ~~"通过大模型进行上下文精简"~~

---

## 3. 多格式文档支持

### 实际实现
`app/rag/source_loader.py` 中的 `SourceLoaderRegistry`：
- `.md` / `.txt` 文件：直接读取文本
- `.pdf` 文件：pymupdf 提取每页文字，按 `[page N]` 分块
- **不支持** Word (.docx)、EPUB、HTML 等格式
- URL 来源：通过 fetch + BeautifulSoup 提取正文

### 论文推荐表述

**安全写法**：
> "系统当前支持 Markdown、纯文本和 PDF 三种本地文档格式，以及网页 URL 来源。文档入库前经过分块（chunking）处理，PDF 按页拆分以保留页级引用信息。"

**可选补充（展示扩展思路）**：
> "通过 SourceLoaderRegistry 的插件化设计，可在未来扩展对 Word/EPUB 等更多格式的支持。"

**避免的写法**：
> ~~"系统支持 PDF、Word、HTML 等多种文档格式"~~
> ~~"支持 Word 文档的解析与入库"~~

---

## 4. Streaming / 流式输出

### 实际实现
`/frontend/execute/stream` 采用 SSE (Server-Sent Events)：
- 以 `artifact` 事件为单位整块推送（whole-artifact emission）
- 每个 artifact 包含完整的生成文本或结构化数据
- 事件序列：`run_started` → `progress` × N → `artifact` × N → `completed`
- **非** token 级流式输出（no per-token streaming）

### 论文推荐表述

**安全写法（推荐）**：
> "系统通过 SSE 协议实现服务端推送，以完整 Artifact 为单位将生成结果推送至前端，前端实时渲染各阶段产物。"

**避免的写法**：
> ~~"系统实现 token 级流式输出"~~
> ~~"用户可以看到打字机效果的逐字生成"~~

**如果要提流式优势**：
> "相比轮询方式，SSE 推送机制实现了服务端到客户端的实时结果推送，降低响应延迟感知。"

---

## 5. 意图识别 / Intent Detection

### 实际实现
系统中**无独立的意图识别模块**。任务类型由前端显式指定：
- 前端通过 `TaskType`（chat / summarize / compare / search / structured_generation）告知后端
- 后端通过 `FrontendFacade.execute()` 路由到对应 Service
- 无 NLU 层面的意图理解

### 论文推荐表述

**安全写法**：
> "系统采用任务类型显式路由机制，前端指定任务类型（问答/摘要/对比），后端统一执行引擎根据类型分发至对应服务。"

**避免的写法**：
> ~~"系统通过意图识别模块自动判断用户query类型"~~
> ~~"实现NLU层面的意图检测与槽位填充"~~

**如果要留口子**：
> "系统设计预留了意图识别扩展接口，后续可接入 NLU 模块实现用户query的自动任务分类。"

---

## 6. LLM 压缩器 / LLM-based Compression

### 实际实现
**未实现**。当前 `TrimmingCompressor` 是纯启发式的字符级裁剪，不涉及 LLM 调用。

### 论文推荐表述

**安全写法**：
> "系统实现了基于词汇重叠的上下文裁剪策略，在压缩比与信息保留之间取得平衡。"

**避免的写法**：
> ~~"使用 LLM 对冗余上下文进行压缩"~~

**可作为后续工作**：
> "后续可引入基于 LLM 的上下文压缩方法，利用大模型的理解能力进一步提升压缩质量。"

---

## 7. IngestStatus 文档生命周期状态

### 实际实现
`SourceState.ingest_status` 字段为自由字符串，代码中只写入 `"ready"`。**无** 正式状态机。

### 论文推荐表述

**安全写法**：
> "文档入库后标记为 ready 状态，可供检索。"

**避免的写法**：
> ~~"实现了完整的文档生命周期状态机（pending → chunking → indexing → ready）"~~

**如果要提状态机**：
> "系统设计预留了文档生命周期状态机扩展，后续可支持 pending / chunking / indexing / ready / failed 等细粒度状态。"

---

## 8. LangGraph / LangChain 使用程度

### 实际实现
`app/workflows/langgraph_pipeline.py`：
- 使用 LangGraph 构建 4 节点线性 RAG 准备图：retrieve → ground → prepare_context → group_by_document
- 仅在 `SummarizeService` 中使用，其他 Service 直接调用
- 有 `_SequentialGraph` fallback，纯 Python 等价实现
- LangChain Core 仅用于 PromptTemplate 构建

### 论文推荐表述

**安全写法**：
> "在摘要生成服务中引入 LangGraph 框架编排检索→筛选→上下文组装→文档分组的标准 RAG 准备流程，实现了工作流逻辑与业务代码的分离。"

**避免的写法**：
> ~~"系统采用 LangGraph 实现复杂的 DAG 工作流编排引擎"~~
> ~~"基于 LangChain/LangGraph 的高级 Agent 编排系统"~~

**核心亮点（可强调）**：
> "LangGraph/LangChain 作为可插拔 Adapter 使用，核心编排逻辑（FrontendFacade → Service）完全独立于框架，符合六边形架构的依赖倒置原则。"

---

## 9. 评测指标

### 实际实现
`app/evaluation/metrics.py`：
- Hit@1/3/5：检索命中率（chunk 或 doc 级别）
- Citation Consistency：结构一致性 + 期望源一致性
- Latency：avg / p50 / p95 / max，按 task_type 分类

### 论文推荐表述

**安全写法**：
> "本文构建了包含检索命中率、引用一致性、响应延迟三个维度的基准评测体系。"

**注意**：需要实际运行评测并报告数据，不要只描述方法而不给数据。

---

## 10. Docker Compose / 容器化

### 实际实现
`Dockerfile` + `docker-compose.yml` 已补充（本次收尾工作新增）。

### 论文推荐表述

**现在可以写**：
> "系统提供 Docker Compose 一键部署配置，支持后端服务的容器化启动与数据持久化。"

---

## 总结：论文中不要过度承诺的清单

| 论文描述 | 实际实现 | 风险 |
|---------|---------|------|
| bge-reranker 重排 | HeuristicReranker | 高（答辩被追问） |
| LLM 上下文压缩 | TrimmingCompressor | 高 |
| Word 文档支持 | 不支持 | 中 |
| Token 级流式输出 | Artifact 整块推送 | 中 |
| 独立意图识别模块 | TaskType 前端指定 | 中 |
| 完整文档状态机 | 只有 "ready" 字符串 | 低 |
| 复杂 LangGraph DAG | 4 节点线性图 | 低 |
