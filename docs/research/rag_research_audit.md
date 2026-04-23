# MindDock RAG 系统深度调研报告

> 调研时间：2026-04-22
> 调研范围：RAG 全链路（ingest → chunk → embed → retrieve → rerank → answer → citation）
> 目标：为毕业设计答辩与后续工程落地提供分阶段改进路线图

---

## A. 当前实现审计

### A.1 Chunking 实现分析

#### 现状

**关键文件：**
- `app/rag/structured_chunker.py` — 结构化 PDF 分块核心实现
- `app/rag/splitter.py` — 通用文本分割（Markdown heading 感知）
- `app/rag/ingest.py` — 分块策略分发（structured_pdf_chunks vs legacy page-mode）

**当前分块策略：**
```python
CHUNK_MAX_TOKENS = 600
CHUNK_MIN_TOKENS = 80
CHUNK_OVERLAP_TOKENS = 80
```

**结构化分块流程（`structured_chunker.py`）：**
1. **Block 提取阶段**（`extract_blocks_from_page`）：用 pymupdf 提取页面 blocks，分类为 `HEADING | PARAGRAPH | TABLE_LIKE | CAPTION | LIST_ITEM | OTHER`
2. **Block 清理阶段**（`clean_block_text`）：归一化空白、合并连字符行尾
3. **Chunk 生成阶段**（`blocks_to_chunks`）：
   - Heading → 独立 chunk（自身 heading token < 600 则直接 emit）
   - Paragraph/ListItem → 累积到 ~600 tokens 后 flush
   - TABLE_LIKE → 始终独立成块，不与文本合并
   - CAPTION → 尝试合并到前一张表，否则独立 emit
   - 超长段落 → 字符级滑动窗口 fallback

**token 估算（`_estimate_tokens`）：**
```python
cjk_chars / 1.5 + english_words
```
简单但存在误差，尤其对于中英混合文本。

#### 根因问题识别

| 问题 | 根因位置 | 现象 |
|------|---------|------|
| **句子中断** | `_sliding_window` 使用字符级切分（`char_size = int(CHUNK_MAX_TOKENS * 1.5)`），不做句子边界检测 | 超长段落按固定字符数硬切，破坏句子完整性 |
| **单词切断** | 同上，字符级滑动窗口不感知词汇边界 | 英文单词被从中间切开 |
| **chunk 边界不自然** | `_flush_paragraphs` 只检查 token 总量，不检查语义断点 | 相关句子被强行分到不同 chunk |
| **heading 处理过于简单** | `MAX_HEADING_CHARS = 200` 以上的 heading 当 paragraph 处理，但 paragraph 累积逻辑中无 heading 感知 | 长 heading 的后续内容丢失 section 归属 |
| **表格独立成块但无文本描述** | TABLE_LIKE 直接 emit 原始表格文本，未做表格结构解析 | 表格内容检索匹配率低 |

---

### A.2 Retrieval / Rerank / Citation 实现分析

#### Retrieval 现状

**关键文件：**
- `app/rag/vectorstore.py` — Chroma 向量存储封装
- `app/rag/hybrid_retrieval.py` — BM25 + Dense + RRF 混合检索
- `app/services/search_service.py` — 检索服务入口

**检索配置（`hybrid_retrieval.py`）：**
```python
bm25_top_k = 50        # BM25 召回候选数
rrf_k = 60             # RRF 融合常数
dense_top_k = top_k    # Dense 召回数 = 用户请求的 top_k
```

**混合检索流程：**
1. 并行执行 Chroma dense search + BM25 lexical search
2. RRF 融合：`fused[idx] += 1.0 / (rrf_k + rank)`
3. 重建结果时处理"仅 BM25 命中"的边界情况（代码中有 bug：当 chunk 只在 BM25 中时，用 `with_updates(chunk_id=bm25_chunk_id)` 但未重新获取完整的 chunk metadata）

**Distance threshold 过滤（`grounded_generation.py`）：**
```python
MAX_EVIDENCE_DISTANCE = 1.5  # cosine distance 上限
PARTIAL_SUPPORT_DISTANCE = 1.0  # 强证据阈值
```

#### Rerank 现状

**关键文件：** `app/rag/postprocess.py`

**当前实现（`HeuristicReranker`）：**
```python
total = (distance_score * 0.45) + (lexical_overlap * 0.40) + (metadata_overlap * 0.10) + short_bonus
```

**问题：**
- 权重固定（0.45/0.40/0.10），无数据驱动调优
- 无 cross-encoder 重排，纯启发式
- short_bonus 倾向于短 chunk，但短 chunk 不一定语义完整

#### Compressor 现状

**当前实现（`TrimmingCompressor`）：**
```python
_MAX_COMPRESSED_HITS = 4          # 最多保留 4 个 chunk
_MAX_COMPRESSED_SENTENCES = 2     # 每个 chunk 最多 2 个句子
_MAX_COMPRESSED_CHARS = 280       # 每个 chunk 压缩后最多 280 字符
```

**问题：**
- 句子切分用正则 `(?<=[.!?。！？])\s+`，对英文以外语言效果差
- 句子级 overlap score 排序，可能丢失核心上下文
- **句子级压缩后 chunk 文本变短，citation snippet 引用的是压缩后文本，可能与原 chunk 不一致** → 引用精确度下降的根因之一

#### Citation 绑定现状

**关键文件：** `app/services/grounded_generation.py`

**Citation 构建流程：**
```python
build_citation(hit)  # 从 RetrievedChunk 构建 CitationRecord
# 使用 hit.citation_text() 即 original_text 或 text（压缩后）
snippet = text[:SNIPPET_LIMIT]  # SNIPPET_LIMIT = 120 字符
```

**核心问题：**
- `citation_text()` 返回 `original_text or text`，但 `text` 已经被 `TrimmingCompressor` 压缩成 2 句/280 字符
- citation 引用的是**压缩后**的文本片段，而非完整 chunk 中的位置
- **引用与答案之间的绑定弱**——LLM 生成的答案中的陈述可能对应压缩文本之外的原 chunk 内容

---

### A.3 多模态支持现状

**当前仅支持：**
- 文本（Markdown、纯文本、PDF 文本）
- URL 网页抓取（`source_loader.py` 中的 `URLSourceLoader`）

**完全缺失：**
- 图片（嵌入 PDF 的图片、独立图片文件）
- 表格（当前表格提取为 TABLE_LIKE block，但仅保留原始文本，无结构化表示）
- 视频
- 音频

**PDF 中的图片处理：**
```python
# pdf_parser.py
if block.get("type") != 0:  # type 1 = image, type 2 = math
    continue  # 直接跳过图片 block
```

---

## B. 问题拆解与根因分析

### B.1 检索与引用不准

#### 现象
- 检索召回的 chunk 与 query 相关性不高
- Citation 存在"看起来引用了，但实际上不够精确"的问题
- Answer 中提到的内容在引用 chunk 中找不到对应原文

#### 根因

**链路层问题（从 retrieval 到 citation 的多跳降级）：**

1. **检索阶段**：`top_k` 默认值偏小（chat 用 3，search 用 5），且 `MAX_EVIDENCE_DISTANCE = 1.5` 的阈值较宽松，可能纳入低相关 chunk

2. **Rerank 阶段**：启发式权重无数据支撑，短文本 bonus 反而惩罚了信息密度高但稍长的 chunk

3. **Compress 阶段**：这是最关键的降级点——`TrimmingCompressor` 将 chunk 压缩到 280 字符/2 句，**丢失了大量上下文**，但 citation 绑定基于压缩后文本

4. **Citation 绑定阶段**：`build_citation` 取 `hit.citation_text()[:SNIPPET_LIMIT]`，snippet 截取的是压缩后文本的**开头**，而非 LLM 答案实际引用原 chunk 的具体位置

**架构问题：**
- Compression 和 Citation 是两个独立步骤，Citation 不知道 LLM 实际用了哪句
- 没有"answer 生成时动态绑定 citation"的机制（属于 sentence-level attribution 范畴）

#### 对系统链路的影响
```
检索 → Rerank → Compress → LLM 生成 → Citation 绑定
                        ↑
                  关键降级点：压缩后的文本被当作 citation 基础
```

---

### B.2 Chunk 边界不合理

#### 现象
- 句子中断、单词切断
- chunk 边界不自然，破坏语义完整性
- citation 引用不精确（部分是这个问题的下游）

#### 根因

**两层问题叠加：**

1. **Block 提取层面（pymupdf）**：
   - pymupdf 的 `page.get_text("dict")` 返回的 blocks 本身可能是按物理行（line）分割的，不一定按语义行分割
   - 对于复杂 PDF（多栏、表格跨栏），block 边界可能混乱

2. **Chunk 生成层面（`blocks_to_chunks`）**：
   - `_flush_paragraphs()` 累积逻辑：累积到 `CHUNK_MAX_TOKENS * 0.95` 就 flush，不保证语义完整性
   - 超长段落 fallback 到 `_sliding_window()`，这是**字符级**切分，不是 token 级，更不是句子级
   - `_sliding_window` 代码：
   ```python
   char_size = int(CHUNK_MAX_TOKENS * 1.5)  # 约 900 字符
   step = max(1, size - overlap)
   for start in range(0, len(text), step):
       w = text[start: start + size].strip()  # 纯字符切片
   ```
   **这是句子中断的直接根因。**

3. **Overlap 策略问题**：
   - 当前 overlap 是 token 级（80 tokens），但 fallback 切分用字符级
   - 中文文本 token 估算不准确（`cjk_chars / 1.5`），导致实际 chunk 大小偏差

#### 与设计目标的冲突
- 设计目标：可追溯问答、精确引用
- 当前实现：chunk 边界由 token 硬切决定，不保证语义完整性
- 冲突点：citation 引用的文本片段可能截断了自然语义单元

---

### B.3 多模态缺失

#### 现象
- 无法处理 PDF 中的图片、图表
- 无法处理独立图片文件
- 无法处理视频、音频内容

#### 根因

**当前架构是纯文本 RAG：**
- `pymupdf` PDF parser 直接跳过 type 1 (image) blocks
- 没有 image embedding pipeline
- 没有视频/音频处理 pipeline
- 没有多模态融合机制

**影响：**
- 大量知识以图片形式存在（PPT 截图、扫描 PDF 中的图表、论文中的 figure）
- 这些知识完全无法被检索和问答

---

## C. 外部调研综述

### C.1 Chunking 策略

#### 该方向在解决什么问题
如何将文档切成语义完整的小单元，使得检索时能召回最相关的内容，且 chunk 本身在被引用时语义自足。

#### 主流技术路线

| 路线 | 核心思想 | 代表工作/工具 |
|------|---------|-------------|
| **Fixed-size（当前方案）** | 按 token/字符数硬切 | 简单但破坏语义 |
| **Recursive splitting** | 层级化切分：先段落 → 再句子 → 最后单词 | LangChain `RecursiveTextSplitter` |
| **Sentence-aware** | 先识别句子边界，在句子级别做累积 | 解决句子中断问题 |
| **Semantic chunking** | 用 embedding 相似度检测语义断点 | Stanford 2025 报告：+15% F1 |
| **Hierarchical / Parent-Context** | 保留父子层级：细粒度检索 + 粗粒度上下文 | Parent-Context 达 0.88 Precision |
| **Structure-aware** | 利用 PDF 布局/heading 层级/Markdown 结构 | 当前 structured_chunker 已在做 |
| **LLM-powered** | 用 LLM 判断 chunk 边界 | 成本高，适合高价值文档 |

#### 关键发现（NVIDIA 2024 Benchmark）
- **Page-level chunking** 在结构化文档上表现最好（0.648 accuracy）
- 但仅当 PDF 分页有物理意义时有效（不是文本导出的人工分页）
- Semantic chunking 可提升 9-20% 检索精度，但增加 embedding 计算成本
- **10-20% overlap** 可恢复 60-70% 的边界损失问题

#### 适合 MindDock 的方案
- **短期**：在现有 structure-aware 基础上，修复 `_sliding_window` 的字符级切分为**句子级切分**
- **中期**：引入 sentence-aware overlap（句子级重叠）
- **长期**：Parent-Context chunking（细检索 + 粗上下文）

#### 关键来源
- ByteTools "RAG Chunking Best Practices 2026"
- NVIDIA 2024 RAG Chunking Benchmark
- Stanford AI Lab "Semantic Chunking for RAG" (2025)
- Ailog "Advanced Chunking Strategies for RAG Systems in 2025"

---

### C.2 Hybrid Retrieval 与 Reranking

#### 该方向在解决什么问题
单一 dense retrieval 对精确词匹配（专业术语、缩写、代码 ID）召回差；reranking 在宽召回基础上精筛top结果。

#### 主流技术路线

**Hybrid Retrieval 三要素：**
1. **Sparse (BM25/SPLADE)**：精确词匹配，术语/ID/缩写友好
2. **Dense (Vector)**：语义相似性，释义/同义词友好
3. **Fusion (RRF/Convex)**：融合排名

**Reranking 两阶段：**
1. **Bi-encoder rerank**：候选重排（CoHERE rerank, sentence-transformers cross-encoder）
2. **LLM-as-judge**：用 LLM 评判答案质量（成本高）

**关键参数：**
- RRF `k=60` 是零配置默认，较鲁棒
- BM25 top_k=50 配合 top_k retrieval=20 是常见配置
- Cross-encoder rerank 在 top-3 可提升 10-25% precision

#### MindDock 现状分析
- ✅ 已实现 BM25 + Dense + RRF（`hybrid_retrieval.py`）
- ❌ 无 cross-encoder rerank（只有启发式 `HeuristicReranker`）
- ⚠️ BM25 index 在首次检索时懒加载（`_scan_all_chunks`），大规模语料初始化慢

#### 适合 MindDock 的方案
- **短期**：评估现有 RRF 效果，如需要可用 lightweight cross-encoder（如 `cross-encoder/ms-marco-MiniLM-L-6-v2`）替代启发式 rerank
- **中期**：query decomposition / query rewrite（对复杂问题拆分子查询）
- **不推荐**：过早引入 LLM-as-judge rerank（延迟高、成本高）

#### 关键来源
- DEV Community "15 Engineering Decisions Behind RAG Hybrid Search" (2026)
- Prem AI Blog "Hybrid Search for RAG: BM25, SPLADE, and Vector Search Combined"
- Ranjan Kumar "Building Hybrid Search That Actually Works" (2026)

---

### C.3 Citation / Answer Attribution

#### 该方向在解决什么问题
LLM 生成的答案中，哪些陈述对应哪些检索到的证据？如何做到**可验证**的引用，而非幻觉引用？

#### 核心概念区分

| 概念 | 定义 | 论文 |
|------|------|------|
| **Citation Correctness** | 引用是否匹配人类作者对同一文本会使用的引用 | Wang et al. 2024 |
| **Citation Faithfulness** | 引用是否真实反映 LLM 的推理过程（防后合理化） | Wallat et al. 2024 |
| **Sentence-level Attribution** | 每句话对应哪个证据 | Xia et al. 2025 (NAACL) |
| **Post-rationalization** | LLM 先生成答案再补充引用，引用与推理脱节 | 55-57% 的 citation 存在此问题 |

#### 主流技术路线

| 路线 | 方法 | 效果 |
|------|------|------|
| **Self-citation prompting** | 让 LLM 在生成时附带引用 | 简单但 faithfulness 低 |
| **MIRAGE** | 用模型内部状态做 attribution | EMNLP 2024，抽取式 QA 高一致 |
| **ReClaim** | 交替生成 reference 和 claim，句子级引用 | NAACL 2025，90% citation accuracy |
| **VeriCite** | 三阶段：生成→NLI验证→精化 | SIGIR 2025，显著提升 citation 质量 |
| **CiteGuard** | retrieval-aware agent framework | CiteME benchmark 68.1%（接近人类 69.2%） |
| **LoDIT** | 引入了 identifier-based document grounding | Trust-Align benchmark，显著改进 faithfulness |

#### MindDock 现状问题

当前 pipeline 的 citation 绑定是**生成后处理**（post-generation），不是**生成时绑定**（in-generation）：

```
当前流程：检索 → 压缩 → LLM生成 → build_citation（从compressed chunk提取）
问题：LLM 可能引用了 compressed chunk 之外的 original chunk 内容，但 citation 只引用了 compressed 部分
```

这属于 **citation faithfulness** 问题（引用未能忠实反映 LLM 的实际推理过程）。

#### 适合 MindDock 的方案
- **短期**：修复 `TrimmingCompressor` 的句子级压缩逻辑，确保 citation snippet 来自压缩文本的语义中心
- **中期**：引入 sentence-level evidence selection（在 rerank 阶段就选择句子级证据，而非 chunk 级）
- **长期**：参考 ReClaim 的 interleaved reference-claim 机制，或引入 NLI-based evidence verification（VeriCite 路线）

#### 关键来源
- Xia et al. "Ground Every Sentence" (NAACL Findings 2025) — 90% citation accuracy
- Wang et al. "Model Internals-based Answer Attribution" (EMNLP 2024) — MIRAGE
- Wallat et al. "Is Citation Accuracy Sufficient for Trustworthiness?" (2024) — 57% post-rationalization
- Fan et al. "VeriCite" (SIGIR 2025)
- Choi et al. "CiteGuard" (arXiv 2025)

---

### C.4 多模态 RAG

#### 该方向在解决什么问题
如何让 RAG 系统处理图片、表格、视频、音频等非文本模态，并在生成答案时正确引用它们。

#### 主流技术路线

| 路线 | 方法 | 代表工作 |
|------|------|---------|
| ** Multimodal embedding** | 用 CLIP/llava 等模型将图片和文本映射到同一向量空间 | KX Systems Guide, Gemini Multimodal RAG |
| **Modality-specific pipeline** | 各模态独立处理（OCR→文本化 / ASR→文本化）再融合 | MMORE (swiss-ai), Multi-RAG |
| **Layout-aware parsing** | 解析 PDF 布局，区分文本/表格/图片区域 | 当前 pymupdf 已有 block 概念 |
| **Table extraction** | 结构化表格内容，便于精确检索 | 当前只有 TABLE_LIKE 文本化 |
| **Video segmentation** | ASR + OCR + keyframe caption + segment metadata | Gemini Lab, Multi-RAG (arXiv 2025) |
| **Unified multimodal format** | 统一的多模态 chunk 格式（text + image description + layout） | MMORE pipeline |

#### 关键发现

**对于个人项目/毕业设计，第一阶段推荐：**
1. **文档视觉理解 + 文本化索引**（不是直接上完整多模态 embedding）
   - PDF images → OCR + captioning → 作为文本 chunk 索引
   - 表格 → 结构化提取（如 `tabby`/`camelot`）→ 保留行列结构信息
   - 这样做成本低、答辩可解释性强

2. **渐进式多模态：**
   - v1：文本-only（当前）
   - v2：图片 OCR + captioning → 文本化接入现有 pipeline
   - v3：多模态 embedding（CLIP 之类）

**Video RAG 推荐第一版路径：**
- ASR 提取音频文本
- OCR 提取字幕/文字
- Keyframe captioning（用 LLM 描述关键帧）
- Segment metadata（时间戳 + 描述）
- **Text-first retrieval**（用户 query 还是文本，匹配上述文本 metadata）

#### 适合 MindDock 的方案
- **立即可行**：PDF 图片 block 的 OCR + captioning 化（作为额外文本 chunk）
- **次年可做**：独立图片文件接入（`FileSourceLoader` 扩展）
- **长期**：视频切片 + ASR + keyframe caption（参考 Multi-RAG 的架构）

#### 关键来源
- KX Systems "Guide to Multimodal RAG for Images and Text" (2024)
- Gemini Lab "Building Multimodal RAG Systems with Gemini" (2026)
- Gemini Lab "Gemini API Multimodal RAG Pipeline Production Guide" (2026)
- swiss-ai/MMORE GitHub (multimodal open RAG pipeline)
- Mao et al. "Multi-RAG: A Multimodal Retrieval-Augmented Generation System for Adaptive Video Understanding" (arXiv 2025)
- aclanthology "Multimodal Retrieval-Augmented Generation: Unified Information Processing" (MAGMaR 2025)

---

## D. 面向 MindDock 的候选改进方案矩阵

| 方案 | 解决的问题 | 预期收益 | 实现复杂度 | 风险 | 适合毕设写作 | 适合当前落地 | 推荐优先级 |
|------|-----------|---------|----------|------|------------|------------|-----------|
| **修复 `_sliding_window` 为句子级切分** | 句子中断/单词切断 | 显著改善 chunk 质量，减少语义破坏 | 低 | 需验证句子检测对中文效果 | ✅ 非常适合 | ✅ 立即可做 | **P0** |
| **Sentence-aware overlap** | chunk 边界不自然 | 边界处上下文保留完整 | 低-中 | 增加 chunk 数量 | ✅ 适合 | ✅ 容易做 | **P0** |
| **评估并替换为 lightweight cross-encoder rerank** | retrieval 精度不足 | top-3/5 precision 提升 10-20% | 中 | 需 GPU 或 API | ✅ 适合（有 benchmark 对比） | ⚠️ 需评测验证 | **P1** |
| **修复 citation 绑定：压缩chunk语义中心而非开头** | citation 引用不精确 | citation 指向更相关内容 | 低 | 需改 TrimmingCompressor 逻辑 | ✅ 适合 | ✅ 容易做 | **P0** |
| **Parent-Context chunking（细检索+粗上下文）** | chunk 过小/过大导致上下文丢失 | 兼顾精确检索和完整上下文 | 中-高 | 需改索引结构，API 兼容性 | ✅ 适合（架构清晰） | ⚠️ 需规划 | **P1** |
| **Query decomposition** | 复杂query召回差 | 提升复杂问题检索质量 | 中 | 引入额外 LLM 调用延迟 | ✅ 适合（方法论丰富） | ⚠️ 需评估 ROI | **P2** |
| **PDF图片 OCR + captioning 文本化** | 多模态缺失 | 图片内容可检索 | 中 | OCR 质量依赖 | ✅ 适合（视觉理解热点） | ✅ 独立模块 | **P1** |
| **表格结构化提取** | 表格语义丢失 | 表格行列结构可检索 | 中-高 | 表格格式多样 | ✅ 适合 | ⚠️ 需选型 | **P2** |
| **视频 ASR + keyframe caption → 文本检索** | 视频内容缺失 | 视频字幕/关键帧可检索 | 高 | 工程量大 | ✅ 适合（前沿方向） | ❌ 当前阶段过重 | **P3** |
| **Full multimodal embedding (CLIP)** | 跨模态语义检索 | 图片/视频直接可检索 | 高 | 架构重构大 | ✅ 适合（前沿方向） | ❌ 当前阶段过重 | **P3** |
| **Sentence-level attribution (ReClaim-style)** | citation faithfulness 低 | 90% citation accuracy | 高 | 需改 LLM 生成流程 | ✅ 适合（NAACL 2025） | ❌ 当前阶段过重 | **P2** |
| **NLI-based evidence verification (VeriCite)** | 答案 faithfulness | 提升引用可靠性 | 中-高 | 增加验证延迟 | ✅ 适合 | ⚠️ 可做但非首选 | **P2** |

---

## E. 推荐路线图

### Phase 0：立即修复（1-2 周，可独立测试）

**目标：** 修复已知最明显的 chunk 边界和 citation 精确度问题

**修改清单：**

#### E.0.1 修复 `_sliding_window` 字符级切分为句子级

**文件：** `app/rag/structured_chunker.py`

**问题：** 第 624-634 行的 `_sliding_window` 使用纯字符切片，破坏句子完整性。

**修复方案：**
```python
# 替换字符级 sliding window 为句子级
_SENTENCE_SPLITTER = re.compile(r'(?<=[.!?。！？；;\n])+\s+')

def _sliding_window(text: str, size: int, overlap: int) -> list[str]:
    """Sentence-level sliding window for oversized paragraphs."""
    sentences = [s.strip() for s in _SENTENCE_SPLITTER.split(text) if s.strip()]
    windows: list[str] = []
    current_window: list[str] = []
    current_len = 0
    
    for sentence in sentences:
        sent_len = len(sentence)
        if current_len + sent_len > size and current_window:
            windows.append(" ".join(current_window))
            # Overlap: keep last 1-2 sentences
            overlap_size = 0
            overlap_sentences = []
            for s in reversed(current_window):
                overlap_size += len(s) + 1
                overlap_sentences.insert(0, s)
                if overlap_size >= overlap:
                    break
            current_window = overlap_sentences
            current_len = sum(len(s) + 1 for s in current_window)
        current_window.append(sentence)
        current_len += sent_len + 1
    
    if current_window:
        windows.append(" ".join(current_window))
    return [w for w in windows if w]
```

**预期收益：** 超长段落不再被字符级切断，句子保持完整

#### E.0.2 修复 `TrimmingCompressor` 的 citation 语义中心问题

**文件：** `app/rag/postprocess.py`

**问题：** 当前压缩取前 2 句/280 字符，citation 引用的是 chunk 开头，而非 LLM 实际引用的位置。

**修复方案：** 改为选择与 query overlap 最高的句子，而非从头取：
```python
# 在 TrimmingCompressor.compress 中
# 替换：
# kept_sentences = ranked_sentences[:_MAX_COMPRESSED_SENTENCES]
# 改为：选择与 query 最相关的句子（已在 ranked_sentences 中排序）
# 但改为取"相关性最高的连续句子块"，而非前 N 句
# 同时在 CitationRecord 中记录实际引用的句子，而非 chunk 开头
```

#### E.0.3 改进 token 估算精度

**文件：** `app/rag/structured_chunker.py` 中的 `_estimate_tokens`

**问题：** `cjk_chars / 1.5 + english_words` 对中英混合文本误差大。

**修复方案：** 使用 `tiktoken` 或 `transformers` 的 tokenizer 做准确 token 计数（可选，但能提升 chunk 大小均匀度）。

---

### Phase 1：检索质量提升（2-4 周）

**目标：** 在 Phase 0 基础上，用轻量级方法提升检索精度

**修改清单：**

#### E.1.1 引入 lightweight cross-encoder rerank

**文件：** `app/rag/postprocess.py`（新增 `CrossEncoderReranker` 类）

**推荐模型：** `cross-encoder/ms-marco-MiniLM-L-6-v2`（6 层，轻量，CPU 可跑）

**实现路径：**
1. 在 `HeuristicReranker` 和 `NoOpReranker` 之外，新增 `CrossEncoderReranker`
2. 通过 settings 配置选择 reranker 类型
3. 评测：对比 `top-3/5 precision` 在当前知识库上的提升

**评测设计：** 见 Section F

#### E.1.2 调优 RRF k 参数

通过小规模标注数据集（如 50-100 个 query-chunk 对）搜索最优 `rrf_k`（当前默认 60，可能非最优）。

#### E.1.3 BM25 top_k 上调

当前 `bm25_top_k = 50`，考虑上调到 100-200，提升混合检索的召回面。

---

### Phase 2：结构化 Chunking 增强（4-8 周）

**目标：** 在结构化分块基础上引入语义感知

**修改清单：**

#### E.2.1 Sentence-aware overlap

在 `_flush_paragraphs` 中引入句子级 overlap，而非当前 token 级 overlap。

#### E.2.2 Parent-Context Chunking（可选，复杂度较高）

**架构：**
- 索引两个层级：parent chunk（约 2000 tokens）+ child chunk（约 300-600 tokens）
- 检索时召回 child chunks，生成时用对应 parent chunk 提供上下文
- Chroma metadata 中存储 `parent_id`

**适合场景：** 论文、书籍等长文档，需要长上下文才能回答的场景。

---

### Phase 3：多模态接入（8-16 周，长期目标）

**目标：** 支持图片、表格、视频内容的接入和检索

#### E.3.1 PDF 图片 OCR + Captioning（Phase 3a，8-12 周）

**实现路径：**
1. 修改 `pdf_parser.py`：对 type=1 的 image blocks，调用 OCR API（如 `pytesseract` 本地或云服务）
2. 对 OCR 结果用 LLM 生成 caption
3. 将 caption 作为文本 chunk 接入现有 pipeline
4. metadata 中标记 `block_type: "image_caption"`

#### E.3.2 表格结构化提取（Phase 3b，8-12 周）

**工具选型：** `tabby`（基于深度学习，支持多种表格格式）

**输出：** 结构化 JSON 表示（表头、行、列），存储为 metadata，文本化表示用于检索。

#### E.3.3 视频接入（Phase 3c，12-16 周）

**第一版实现（Text-first）：**
- ASR 提取音频文本（`whisper` 或云 ASR 服务）
- OCR 提取字幕/文字（`pytesseract`）
- Keyframe captioning（每隔 N 秒用 LLM 描述画面）
- 视频 segment metadata（时间戳 + 描述）作为检索字段
- 用户 query 还是文本，匹配上述文本 metadata

**全模态检索（长期）：**
- 引入 CLIP 或等效模型，将视频帧和图片映射到文本向量空间
- 实现跨模态检索（图片 query 匹配视频帧）

---

## F. 评测方案

### F.1 检索评测

#### 数据集设计建议

**Minimum viable benchmark：**
1. 人工标注 50-100 个 (query, relevant_chunks) 对
2. Query 来源：从知识库常见问题中采样，覆盖不同类型（事实性查询、解释性查询、对比查询）
3. relevant_chunks：人工标注每个 query 对应的相关 chunk doc_ids

**评估指标：**
- **Recall@k**（k=1,3,5）：Top-k 中包含相关 chunk 的比例
- **MRR@3**：首个相关 chunk 排名的倒数均值
- **NDCG@5**：考虑排名的质量指标

#### 实现代码框架
```python
# tests/evaluation/test_retrieval.py
import pytest
from app.rag.vectorstore import LangChainChromaStore
from app.rag.hybrid_retrieval import get_hybrid_retrieval_service

class TestRetrievalMetrics:
    def test_recall_at_k(self, annotated_queries):
        """Recall@k on annotated query-chunk pairs."""
        store = LangChainChromaStore()
        for query_data in annotated_queries:
            hits = store.search_by_text(query_data["query"], top_k=5)
            retrieved_ids = {hit.chunk_id for hit in hits}
            relevant_ids = set(query_data["relevant_chunk_ids"])
            recall = len(retrieved_ids & relevant_ids) / len(relevant_ids)
            assert recall >= 0.7  # minimum threshold
```

---

### F.2 Citation 精度评测

#### 评测方法

**Citation Precision（引用精确度）：**
- 人工评估：给定 (answer, citations) 对，判断每个 citation 是否"必要且充分"地支持答案中的对应陈述
- 自动评估（近似）：用 NLI 模型判断 citation 文本是否蕴含答案陈述

**Attribution Accuracy（归属准确度）：**
- 参考 Xia et al. 2025 的 sentence-level attribution 评测
- 将答案切分为句子，每句标记对应的 evidence chunk
- 计算 sentence-level citation accuracy

**Faithfulness Rate（忠诚度）：**
- 检测 post-rationalization：引用是否在生成答案之后补充
- 方法：对比 (answer + citation) vs. 仅 answer 的语义一致性

#### 实现建议
```python
# tests/evaluation/test_citation.py
def test_citation_faithfulness(grounded_answers):
    """Test that citations faithfully reflect LLM's actual evidence usage."""
    for answer_data in grounded_answers:
        citations = answer_data["citations"]
        evidence_texts = [c["snippet"] for c in citations]
        # Use NLI model to check if answer is entailed by evidence
        for citation in citations:
            entailment = nli_model.check_entailment(
                premise=evidence_texts,
                hypothesis=citation["referenced_statement"]
            )
            assert entailment > 0.7, "Citation does not faithfully support answer"
```

---

### F.3 Chunk 质量评测

#### 可操作评测方法

**方法 1：下游任务反推**
- 在固定 query set 上评测 retrieval recall
- Chunk 质量差 → recall 低
- 这是最实用的端到端评测

**方法 2：边界完整性人工抽检**
- 随机抽样 100 个 chunks，人工标注：
  - 句子是否完整？（无切断）
  - chunk 是否语义自足？（可独立理解）
  - chunk 间重叠是否足够？（边界处上下文保留）
- 计算完整性比例

**方法 3：Chunk Size 分布监控**
```python
# 不需要人工的自动化指标
def test_chunk_size_distribution(store):
    chunks = store._scan_all_chunks()
    sizes = [len(c) for c in chunks]
    assert np.percentile(sizes, 95) < 900  # 95% chunk < 900 chars
    assert np.percentile(sizes, 5) > 50    # 5% chunk > 50 chars
```

---

### F.4 多模态场景评测（未来）

**图片 QA 评测：**
- 构建 (image, question, answer, evidence_chunk) 测试集
- 评测：给定图片内容的问题，答案是否正确引用了图片描述 chunk

**视频 QA 评测：**
- 构建 (video_segment, timestamp, question, answer) 测试集
- 评测：答案是否正确引用了对应时间戳的文本描述

---

## G. 最终结论

### 最值得优先做的 3 件事

1. **修复 `_sliding_window` 的字符级切分为句子级切分（Phase 0，1 周）**
   - 直接解决"句子中断/单词切断"这个明显问题
   - 改动范围小，可独立测试，不影响其他模块
   - 对 citation 精确度和检索质量都有正向收益

2. **引入 lightweight cross-encoder rerank（Phase 1，2-3 周）**
   - 当前启发式 rerank 权重无数据支撑，效果有限
   - `ms-marco-MiniLM-L-6-v2` 是经过验证的轻量方案，CPU 可跑
   - 有明确的评测方法（top-k precision），收益可量化

3. **修复 citation 绑定逻辑（Phase 0，1 周）**
   - `TrimmingCompressor` 压缩后 citation 引用 chunk 开头，而非实际引用位置
   - 这是"citation 存在但不精确"问题的直接根因
   - 修复后 citation 质量立即提升，答辩演示效果好

### 最不建议当前做的 2-3 件事

1. **端到端 multimodal embedding（CLIP 等）**
   - 工程量大，架构改动大
   - 答辩时难以解释原理（多模态对齐的内部机制复杂）
   - 建议用"视觉理解 + 文本化"作为过渡方案

2. **LLM-as-judge reranking**
   - 延迟高、成本高
   - 需要额外 API 调用或本地部署
   - 当前阶段投入产出比低

3. **Parent-Context chunking 完整实现**
   - 需要改索引结构（parent_id, child_id 关系）
   - API 兼容性需要处理
   - 收益不确定（仅对长文档场景有显著效果）

### 毕业设计答辩 + 工程可信度最优策略

**核心叙事框架：**

```
问题：RAG 系统中，chunk 边界破坏语义完整性 → 检索召回差 → citation 引用不精确

方案：
  1. Structure-aware chunking → 句子级边界感知（当前实现 + 改进）
  2. Hybrid retrieval → BM25 + Dense + RRF（已实现）+ cross-encoder rerank（改进）
  3. Citation precision → 句子级 evidence selection + citation 绑定修复

评测：
  - Retrieval: Recall@k, MRR
  - Citation: attribution accuracy, faithfulness rate
  - Chunk quality: boundary completeness人工抽检

答辩亮点：
  - 展示 chunk 边界改进前后的对比（截图/日志）
  - 展示 citation 引用在答案中的精确位置（vs 对比系统）
  - 可解释性强：每步改进都有明确动机和可量化收益
```

**论文写作结构建议：**
1. 背景：RAG 系统中的 chunking 问题（引用破坏、检索不准确）
2. 相关工作：structure-aware chunking、hybrid retrieval、citation attribution
3. 方法：
   - 结构化 PDF 分块（已有）+ 句子级边界感知（改进）
   - 混合检索 + reranking（已有 + 改进）
   - 可追溯引用生成（改进）
4. 实验：消融实验（分别验证每项改进的贡献）
5. 结论：改进效果总结 + 局限性 + 未来工作

---

## 附录：关键文件索引

| 模块 | 文件路径 | 核心类/函数 |
|------|---------|-----------|
| PDF 分块 | `app/rag/structured_chunker.py` | `blocks_to_chunks()`, `_sliding_window()` |
| 文本分割 | `app/rag/splitter.py` | `split_text()` |
| 向量存储 | `app/rag/vectorstore.py` | `LangChainChromaStore` |
| 混合检索 | `app/rag/hybrid_retrieval.py` | `HybridRetrievalService` |
| Rerank/压缩 | `app/rag/postprocess.py` | `HeuristicReranker`, `TrimmingCompressor` |
| 引用生成 | `app/services/grounded_generation.py` | `build_citation()`, `select_grounded_hits()` |
| 检索模型 | `app/rag/retrieval_models.py` | `RetrievedChunk`, `CitationRecord` |
| Chat 服务 | `app/services/chat_service.py` | `ChatService.chat()` |
| PDF 解析 | `app/rag/pdf_parser.py` | `extract_pages()`, `extract_page_blocks()` |
| 源头加载 | `app/rag/source_loader.py` | `SourceLoaderRegistry` |
