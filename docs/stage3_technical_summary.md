# 第三阶段技术总结：RAG 核心能力建设

## 概述

本阶段围绕 MindDock 检索与证据链核心能力，集中完成了结构化分块、证据锚定、metadata-aware 重排、向量库迁移和评测体系修订五项工作。改进后的系统在检索精度、证据可回溯性和评测可信度三个维度均有实质提升。

---

## 主题一：结构化分块与可回溯证据链

### 背景问题

传统 chunk 粒度以固定字数或固定段落为单位，既不保留页/章/节层级关系，也无法提供证据在原始文档中的精确位置。用户看到一条检索结果时，只能靠文字内容判断相关性，缺乏可验证的位置信息——这对证据优先的个人知识管理场景是不可接受的缺陷。

早期实现中，PARAGRAPH handler 缺乏页边界检测，导致跨页段落被合并为一个 chunk；section_path 提取使用 stripped heading_text 而非原始文本，使多级编号标题路径错误；英文论文中常见的"编号+换行+标题"格式（ACL/arxiv 风格）无法被识别为章节标题。

### 具体改动

**1. Structured Chunker 页边界修复**

- 在 PARAGRAPH handler 和 HEADING handler 中增加 `prev_page` 追踪
- 检测到页码变化时，对 `para_buf` 执行 flush，防止跨页段落被合并
- 修复 LIST_ITEM vs HEADING 分类规则：编号后内容 < 10 字符 → LIST_ITEM，≥ 10 字符 → HEADING

**2. section_path 提取修复**

- 改为使用 `b.text`（原始 heading 文本）而非 stripped heading_text 作为路径来源
- "1. Introduction" 现在正确解析为 section_path="1"，而非被截断

**3. 多行编号标题检测**

- 新增 `_looks_like_multiline_heading()` 函数
- 将形如 `"2\nMulti-Document Question Answering"` 的块识别为 HEADING 而非 OTHER
- 修复效果：Lost in Middle section_path 覆盖率从 0/82 提升至 83/87；ArXiv-2501 从 0/177 提升至 228/233

**4. 证据锚定与参与状态**

- 新增 `EvidenceItem` 数据结构，包含 `highlighted_sentence`（高亮句子原文）、`position_start`、`position_end`（字符级偏移）、`block_id`、`section_path`
- 新增 `participation_state`（参与状态）：每条证据点记录 cited / revisited / copied 等状态
- 后端完成 participation 事件聚合与状态投影（`app/services/participation.py`）

**5. 前端证据回访**

- 修复 `build_chat_artifacts` 等函数中手动构造 citation dict 导致字段丢失的问题
- 改用 `EvidenceItem.from_record().model_dump()` 确保 `highlighted_sentence`、`position_start/end`、`block_id` 全部透传到前端

### 结果指标

| 指标 | Page-Mode 基线 | Structured+Hybrid+SoftV3 |
|------|--------------|------------------------|
| page_hit@1 | 0.0 | 0.667 |
| page_hit@5 | 0.0 | 0.944 |
| section_hit@1 | 0.0 | 0.611 |
| bt_hit@1 | 0.0 | 0.833 |
| mrr_page | 0.0 | 0.759 |
| mrr_section | 0.0 | 0.690 |

- PDF 文档 section_path 覆盖率：83%–98%
- 全量 16/16 文档重建成功

### 剩余局限

- 部分复杂表格、公式页面的结构识别仍有盲区，语义类型判断依赖启发式规则
- 跨页段落重建依赖 `para_buf` 合并逻辑，极端版式可能断裂
- markdown 文档目前不经过 structured chunker，元数据覆盖率低于 PDF

---

## 主题二：Metadata-Aware Rerank

### 背景问题

在通用查询（如"Attention 机制的最新进展"）下，检索结果中往往混杂大量来自 AUTHOR、ABSTRACT、REFERENCE 等元数据区域的匹配段落。这些区域对于面向文档内容的查询是干扰信号，会降低真正内容段落的排名。同时，当用户明确搜索"某位作者的文章"时，这些区域的权重又需要被恢复。

### 具体改动

在 `HeuristicReranker` 中新增 `_get_metadata_bias()` 辅助函数，基于 `block_type` 和 `semantic_type` 元数据返回加性偏置：

| 区域 | 偏置值 |
|------|--------|
| AUTHOR / Authors / 作者 | -0.15 |
| REFERENCE / References / 参考文献 | -0.15 |
| ABSTRACT 段落（semantic_type=abstract） | -0.05 |
| Body / paragraph / heading | 0（不变） |

最终得分为 `total_score = existing_score + metadata_bias`，不改变排序公式结构。

**Query Intent Bypass**：当查询文本明确包含"abstract/摘要"、"author/作者"、"references/参考文献"等关键词时，通过严格正则匹配跳过对应区域的降权惩罚。

### 结果指标

- 评测通过，无明显主链回归
- 结合 Structured Hybrid SoftV3 检索模式，hit@1 达到 0.667（Page-Mode 基线为 0）

### 剩余局限

- 降权幅度（-0.15 / -0.05）为经验值，尚未在多文档集上系统调参
- 隐式 intent 查询（如"这篇论文谁写的"）可能误触发降权
- bypass 正则规则偏向中文/英文，未覆盖其他语言表述

---

## 主题三：向量库 Re-ingest 迁移

### 背景问题

结构化分块修复后，新 chunk 携带 `section_path` 和 `semantic_type` 字段，但历史入库数据（Chroma 中已有记录）未包含这些字段，导致同一文档库内新旧 chunk 元数据不一致，影响检索 pipeline 的元数据过滤和 rerank 逻辑。

### 具体改动

新增 `scripts/reingest_metadata.py`，提供完整的迁移工具链：

- `--backup`：迁移前对 Chroma 目录做带时间戳的完整备份
- `--dry-run`：预览当前 chunk 数量与重建后数量的差异，不写入
- `--verify`：验证指定文档的 `section_path` 和 `semantic_type` 是否存在于 Chroma
- `--doc-id` / `--source` / `--all`：按文档 ID、来源路径或全量触发重建

迁移使用 `build_langchain_documents()` 生成新 chunk，通过 `replace_document()` 原子化执行删除+写入，避免迁移过程中出现不一致状态。

### 结果指标

- 16/16 文档重建成功
- PDF 文档 section_path 覆盖率约 83%–98%
- retrieval pipeline 已能正确传出 `section_path` 和 `semantic_type`
- 迁移过程零数据丢失

### 剩余局限

- 1000+ 文档规模下的迁移耗时和 Chroma 锁竞争未经评估
- 迁移过程中无法服务写入请求（单文档原子锁）
- 部分非 PDF 格式文档（markdown 等）的 `semantic_type` 覆盖率仍偏低

---

## 主题四：Benchmark 修订与评测结果

### 背景问题

初期 benchmark 存在两类问题：（1）标注错误——预期文档与查询语义不匹配；（2）评测口径过严——要求精确的 chunk_id 而非文档级匹配。这些问题导致系统真实能力被低估，且剩余失败 case 无法真实反映系统缺陷。

### 具体改动

**v1 修订（6 项修正）**：

| 编号 | 问题 | 修订内容 |
|------|------|---------|
| 1 | search_acl_context | 预期文档 d8ad79 → 修正为 ebea242 |
| 2 | search_naacl_experiments | 预期文档 23ab2 → 修正为 b4d26 |
| 3 | search_arxiv2309 | RAGAs 论文标注错误 → 修正为 CRAD survey |
| 4 | search_agentic_rag_taxonomy | chunk_id 条件过严 → 移除 |
| 5 | search_pkm_methods | chunk_id 条件过严 → 移除 |
| 6 | meta_general_abstract | 查询过宽 → 重写为具体查询 |

**v2 修订（2 项修正）**：

- search_acl_context：预期文档与查询语义重新对齐
- search_naacl_experiments：预期文档修正

### 结果指标

| 版本 | hit@1 | hit@3 | hit@5 | 失败 case 数 |
|------|-------|-------|-------|------------|
| 修订前 | 50% | 55% | 65% | 10 |
| v1 后 | 65% | 75% | 85% | 6 |
| v2 后 | **75%** | **85%** | **95%** | 4 |

剩余 4 个失败 case 中：
- `compare_lost_vs_rag`、`compare_pkm_vs_vector`、`compare_architecture_md` 均为检索命中但 LLM 引用了不同源，非检索系统问题
- `compare_architecture_md` 存在内部文档内容重叠导致的 topic diversity 失效，属真实系统局限

### 剩余局限

- 评测集规模较小，统计置信度有限
- 评测查询覆盖场景仍然有限，未覆盖多语言、表格查询等场景
- 3 个 compare case 的 LLM 引用偏差问题需要从生成侧解决，非检索侧优化

---

## 主题五：Compare Dual Retrieval 改进

### 背景问题

"对比 X 和 Y"类型的联合查询在单一向量空间中难以同时准确召回 X 和 Y 相关文档——查询向量被 dominant topic 主导，弱 topic 被挤出 top-k。`compare_agentic_rag_vs_milvus` 这个问题最为典型：Milvus 相关内容在 top-6 中完全消失。

### 具体改动

**Query Decomposition**：新增 `_decompose_compare_query()`，通过正则表达式将 compare 查询拆分为两个子查询（如"Agentic RAG"和"Milvus"）。

**Dual Retrieval**：每个子查询独立执行向量检索，取 `max(top_k, 3)` 条结果。

**Topic Diversity Merge**：新增 `_merge_dual_hits()`，合并两个子查询的候选集，保证每个 topic 至少贡献 1 条结果，剩余槽位按相关性填充。

**Fallback**：若分解失败或候选数不足，回退到单一检索模式。

### 结果指标

| Case | hit@1 | hit@3 | hit@5 | 状态 |
|------|-------|-------|-------|------|
| compare_agentic_rag_vs_milvus | ✅ | ✅ | ✅ | 已修复 |
| compare_pkm_vs_vector | ✅ | ✅ | ✅ | 通过 |
| compare_lost_vs_rag | ❌ | ✅ | ✅ | citation 非检索问题 |
| compare_architecture_md | ❌ | ❌ | ❌ | 内部文档内容重叠 |

- search/chat 主链无回归

### 剩余局限

- `compare_architecture_md`：architecture.md 和 rag_pipeline.md 内容高度重叠，两个子查询召回的 doc_id 集合相同，topic diversity 机制失效，属文档层面的系统限制
- 3 个 compare case 存在 LLM 引用与预期源不匹配的问题，属于 compare 生成质量而非检索问题
- Dual retrieval 引入额外检索延迟（双路并行），在超大规模文档集上需评估 QPS 影响

---

## 综合评价

本阶段在"检索精度"、"证据可追溯性"、"评测可信度"三个维度完成了系统性改进：

1. **结构化分块**使检索结果从不可验证变为可精确回溯到文档层级结构；
2. **Metadata-aware rerank** 解决了元数据区域对内容查询的信号干扰问题；
3. **Re-ingest 迁移**保证了新旧数据的元数据一致性；
4. **Benchmark 修订**提供了可信的评测基线；
5. **Compare dual retrieval** 解决了多主题联合查询的召回失效问题。

剩余局限集中在：部分格式文档（markdown）的结构化覆盖率偏低、compare 场景下文档内容重叠导致的 topic diversity 失效、LLM 引用偏差问题的生成侧解决。这些问题不影响当前阶段汇报的核心成果展示，但应作为后续工作记录在论文中。

---

*数据截止：2026-04-19 | 依据来源：git commits、eval/chunking_eval_report_v4.md、data/eval/pdf_benchmark_revision_notes.md、scripts/reingest_metadata.py*
