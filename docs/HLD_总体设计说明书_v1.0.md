# HLD 总体设计说明书（HLD）
**项目名称**：基于 AI 智能平台的个人知识管理助手（Agentic RAG PKM Assistant）  
**版本**：v1.0  
**日期**：2026-03-04  
**文档状态**：初版（可用于开题/中期/答辩材料支撑）

---

## 0. 设计目标与设计原则

### 0.1 设计目标
- 构建个人私有知识的**外置长期语义记忆**（可扩展、可更新）。  
- 通过 RAG 实现**证据驱动**回答与可追溯引用。  
- 以 Workflow/Skills 实现任务流程固化（可复用、可测试、可观测）。  
- 提供 Profile 配置层实现**通用型可微调**（Prompt + 检索参数 + 输出模板）。  
- 支持“可进可退”：MVP 可交付，进阶模块可逐步叠加。

### 0.2 设计原则
- **高内聚低耦合**：接入、入库、检索、生成、输出、记忆模块边界清晰。  
- **证据优先**：所有知识结论必须可引用溯源；证据不足则降级。  
- **配置优先**：场景差异通过 Profile 配置实现，而非硬编码分叉。  
- **平台优先落地**：优先复用 Coze 平台能力降低工程风险。  
- **可评测**：链路关键节点输出可记录，便于量化对比实验。

---

## 1. 系统总体架构（分层）

```text
┌──────────────────────────────────────────────┐
│ Presentation / Interaction Layer             │
│ - Coze Bot 对话入口 / Web 端配置             │
│ - 文档上传 / URL 剪藏 / 结果展示（引用卡片） │
└───────────────────────┬──────────────────────┘
                        │
┌───────────────────────▼──────────────────────┐
│ Agent Orchestration Layer                     │
│ - 意图路由 Router（选择 skill/workflow）       │
│ - Profile/Preference Manager（通用可微调）     │
│ - Workflow Engine（DAG：检索→生成→校验→输出） │
└───────────────────────┬──────────────────────┘
                        │
┌───────────────────────▼──────────────────────┐
│ RAG Pipeline Layer                            │
│ - Ingestion：解析/清洗/分块/向量化            │
│ - Retrieval：向量检索 + 元数据过滤 +（可选）重排│
│ - Context Assembly：上下文组装与压缩          │
└───────────────────────┬──────────────────────┘
                        │
┌───────────────────────▼──────────────────────┐
│ Storage Layer                                 │
│ - 文档库（原文/清洗文本）                     │
│ - 元数据库（doc/chunk/标签/页码等）           │
│ - 向量索引（平台 KB 或 Vector DB）            │
└───────────────────────┬──────────────────────┘
                        │
┌───────────────────────▼──────────────────────┐
│ Integration Layer (Tools/Plugins)             │
│ - Web Extractor / Notion/Drive（可选）         │
│ - Calendar/Todo（可选）                        │
│ - 通知推送（可选）                             │
└──────────────────────────────────────────────┘
```

---

## 2. 模块设计（Modules）

### 2.1 Presentation/Interaction（交互层）
- 文档接入入口：上传文件、输入 URL、选择标签/时间范围  
- 技能入口：/ask /summarize /mindmap /brief  
- 输出渲染：Markdown + 引用列表（可选：引用卡片/跳转链接）

### 2.2 Router（意图路由）
**输入**：用户自然语言 + 当前 Profile  
**输出**：目标技能 skill_id + 参数（filters/top_k/format）  
**实现策略**：
- 规则优先：若命令式前缀（/ask 等）直接路由  
- 否则轻量分类：基于关键词/短提示词分类为问答/总结/导图/提醒  
- 路由输出进入工作流执行器

### 2.3 Profile/Preference Manager（通用可微调核心）
**职责**：统一管理可配置项并注入各节点：  
- Prompt 模板（系统提示词/输出格式）  
- 检索参数（top_k、过滤条件、是否 rerank）  
- 引用样式（脚注/列表）  
- 启用技能集合（MVP/标准/进阶）

**存储**：轻量 JSON/YAML +（可选）KV/数据库持久化

### 2.4 Ingestion Pipeline（入库管线）
**步骤**：
1) Source Adapter：文件/URL/文本统一为 Document Object  
2) Parser：PDF/HTML/MD 解析为干净文本（尽量保留标题层级与页码）  
3) Cleaner：去噪、规范化（空白、页眉页脚等）  
4) Chunker：按标题/段落切分，必要时递归，设置 overlap  
5) Embedder：生成向量表示  
6) Indexer：写入向量索引与元数据表  
7) Document Card：生成入库报告（chunk 数、状态、标签建议）

**关键策略**：
- 文档 checksum 用于增量更新（Upsert）  
- chunk 保存 section_path 与 location（页码/锚点）用于引用追溯  
- 解析失败提供降级：手动粘贴文本/换解析器

### 2.5 Retrieval Pipeline（检索与上下文组装）
**输入**：query + filters + profile.retrieval  
**输出**：hits（chunk 列表）+ citations（引用信息）

**检索策略**：
- Dense retrieval：embedding 相似度 top_k  
- Metadata filtering：tags/time/source_type  
- 可选 rerank：规则（优先最近/优先某来源）或 cross-encoder 模型  
- Context assembly：  
  - 选择 top_k hits  
  - 超 token 限制时做压缩（先摘要后拼接，或按段落截断）

### 2.6 Generation & Validation（生成与校验）
**生成提示词**由 Profile 决定：
- 输出结构模板  
- 引用强约束（要求每个结论附 citation id）

**可选校验器**（加分项）：
- 引用一致性检查：检查结论是否能在引用片段中找到支持  
- 若失败：触发二次检索（扩大 top_k / 放宽过滤 / query 扩展）或降级回答

### 2.7 Skills（技能设计）
**Skill-A：Cross-Doc QA（必做）**
- 输入：question + filters  
- 流程：rewrite → retrieve → assemble → generate → validate → output  
- 输出：答案 + citations

**Skill-B：Topic Summarize（必做）**
- 输入：topic + scope  
- 流程：retrieve → group by doc → Map summaries → Reduce synthesis → citations  
- 输出：主题报告（要点/对比/行动）+ citations

**Skill-C：Mindmap（推荐）**
- 输入：topic  
- 流程：retrieve → outline JSON → convert Mermaid → output  
- 输出：Mermaid mindmap + citations（可选）

**Skill-D：Brief/Reminder（可选）**
- 输入：schedule/todo + knowledge cues  
- 流程：trigger → fetch → generate briefing → notify  
- 输出：简报/提醒消息

---

## 3. 数据结构与存储设计（Data Design）

### 3.1 数据对象（与 SRS 对齐）
- Document、Chunk、Preference/Profile

### 3.2 存储实现选项
**Option A（推荐）：平台知识库**
- 依赖平台完成 embedding 与向量索引  
- 你负责：入库前处理、检索策略与引用规则、工作流编排

**Option B（增强）：自建向量库**
- 向量库：Qdrant/Milvus/pgvector  
- 元数据：SQLite/PostgreSQL  
- 通过 Tool/Plugin 暴露检索 API 给工作流调用

> 推荐路线：A 主线 + B 作为扩展/对比实验（可进可退）。

---

## 4. 工作流设计（DAG）示例

### 4.1 跨文档问答 DAG（简化）
```text
[Input]
  ↓
[Load Profile/Prefs]
  ↓
[Query Rewrite?]
  ↓
[Vector Search(top_k, filters)]
  ↓
[Rerank?]
  ↓
[Assemble Context + Citations]
  ↓
[LLM Generate (Answer + Cite IDs)]
  ↓
[Validate?]
  ↓
[Render Output]
```

### 4.2 Map-Reduce 总结 DAG（简化）
```text
[Input Topic/Scope]
  ↓
[Retrieve Candidate Chunks]
  ↓
[Group by Document]
  ↓
[Map: per-doc summary]
  ↓
[Reduce: global synthesis]
  ↓
[Attach Citations]
  ↓
[Render Report]
```

---

## 5. 接口设计（APIs / Tool Specs）

### 5.1 内部接口
- Router.route(text, profile) -> skill_id, params  
- Ingest.run(document_object) -> doc_id, status  
- Retrieve.search(query, filters, top_k) -> hits  
- Cite.build(hits, style) -> citations  
- Generate.run(context, template) -> draft  
- Validate.check(draft, citations) -> pass/fail + reasons

### 5.2 对外工具接口
沿用 SRS 的 Tool-1~Tool-5 规范（JSON schema）。建议每个工具包含 version 字段。

---

## 6. 安全与隐私设计（Security/Privacy）
- 数据最小化：只存必要内容与索引，敏感字段脱敏（如邮件/手机号）。  
- 授权隔离：外部数据源通过 OAuth/token 管理；token 不写日志。  
- 删除机制：支持按 doc_id 删除与重建索引。  
- 日志分级：业务日志（统计）与内容日志（默认关闭或截断）。

---

## 7. 可观测性与评测（Observability & Evaluation）
- 记录每次调用的：query、filters、top_k、命中 doc_id/chunk_id、生成 token、引用数  
- 评测集：至少 30 个问题（跨文档/对比/总结类）  
- 指标：Top-k 命中率、引用一致性、人工评分（正确性/可读性/可用性）

---

## 8. 技术深度与难度评估（对本科合理性）
- **系统工程能力**：模块化设计、接口定义、工作流编排、异常处理、测试评测  
- **信息检索能力**：分块、向量检索、过滤与（可选）重排  
- **LLM 应用工程**：证据约束提示词、输出结构化、偏好记忆注入  
- **趋势匹配**：RAG + Agentic workflow + tool calling 属当前主流落地方向  
- **风险点**：文档解析质量与检索调参；可通过“证据不足降级”保证稳定演示

结论：整体达到本科中高水平，且工程可控、论文可量化。

---

## 9. 可进可退路线图（Scalable Roadmap）
- **MVP**：平台 KB + 问答/总结 + 引用 + 偏好模板  
- **标准版**：+导图 + 更完善引用卡片 + 系统评测报告  
- **进阶版**：+自建向量库/混合检索/rerank + 校验器/二次检索 + 主动提醒

---

## 10. 成品质量预估（Forecast）
若按“标准版”实施：
- 演示观感：高（技能清晰、引用可追溯、导图可视化）  
- 工程完整性：中高（模块/接口/日志/评测齐全）  
- 学术表述：中高（可对比实验与量化指标）  
- 稳定性：中（依赖解析/检索质量；降级机制可显著降低翻车）

---

## 11. 附录：Profile 示例（与 SRS 对齐）
见 SRS 第 8 章 Profile YAML 示例，可作为系统配置文件或对话指令生成的结构化配置。
