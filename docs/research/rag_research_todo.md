# RAG 系统改进任务清单

> 基于 `docs/research/rag_research_audit.md` 的调研结果整理
> 优先级说明：P0 = 立即可做（1-2周），P1 = 下一阶段（2-4周），P2 = 中期目标（4-8周），P3 = 长期目标

---

## Phase 0：立即修复（P0）

### [ ] E.0.1 修复 `_sliding_window` 为句子级切分
**文件：** `app/rag/structured_chunker.py`
**问题：** 第 624-634 行字符级切分导致句子中断
**操作：**
- [ ] 实现 `_SENTENCE_SPLITTER` 正则（支持中英文句号）
- [ ] 重写 `_sliding_window` 为句子级
- [ ] 添加单元测试（长段落应被句子级切分）

### [ ] E.0.2 修复 citation 语义中心问题
**文件：** `app/rag/postprocess.py`
**问题：** `TrimmingCompressor` 压缩后 citation 引用 chunk 开头，而非语义中心
**操作：**
- [ ] 改 `TrimmingCompressor.compress` 选择与 query 最相关的连续句子块
- [ ] 确保 `CitationRecord.snippet` 来自实际引用的句子

### [ ] E.0.3 改进 token 估算精度（可选）
**文件：** `app/rag/structured_chunker.py`
**操作：**
- [ ] 评估 `tiktoken` 作为准确 token 计数方案
- [ ] 或保持当前估算（`cjk_chars / 1.5 + english_words`）

---

## Phase 1：检索质量提升（P1）

### [ ] E.1.1 引入 lightweight cross-encoder rerank
**文件：** `app/rag/postprocess.py`
**依赖：** 安装 `sentence-transformers`
**操作：**
- [ ] 新增 `CrossEncoderReranker` 类
- [ ] 在 `get_reranker()` 工厂中添加配置选项
- [ ] 评测：对比 `HeuristicReranker` vs `CrossEncoderReranker` 的 top-3/5 precision

### [ ] E.1.2 调优 RRF k 参数
**文件：** `app/rag/hybrid_retrieval.py`
**操作：**
- [ ] 构建 50-100 个标注 query-chunk 对
- [ ] Grid search `rrf_k` ∈ {20, 40, 60, 80, 100}
- [ ] 选择最优 k 值

### [ ] E.1.3 BM25 top_k 上调
**文件：** `app/rag/hybrid_retrieval.py` 或 `app/core/config.py`
**操作：**
- [ ] 将 `bm25_top_k` 从 50 调整为 100-200
- [ ] 验证对召回率的提升

---

## Phase 2：结构化 Chunking 增强（P2）

### [ ] E.2.1 Sentence-aware overlap
**文件：** `app/rag/structured_chunker.py`
**操作：**
- [ ] 在 `_flush_paragraphs` 中实现句子级 overlap（保留最后一个完整句子）
- [ ] 调整 `CHUNK_OVERLAP_TOKENS` 配置

### [ ] E.2.2 Parent-Context Chunking（可选，复杂度高）
**文件：** `app/rag/ingest.py`, `app/rag/vectorstore.py`
**操作：**
- [ ] 设计 parent-child chunk 元数据 schema
- [ ] 修改 ingest pipeline 支持双层级
- [ ] 修改 retrieval 返回 parent chunk context
- [ ] 评估复杂度，非首选

---

## Phase 3：多模态接入（P2/P3）

### [ ] E.3.1 PDF 图片 OCR + Captioning 文本化（P2）
**文件：** `app/rag/pdf_parser.py`
**依赖：** `pytesseract` 或云 OCR API
**操作：**
- [ ] 修改 `extract_page_blocks` 对 type=1 (image) blocks 调用 OCR
- [ ] 对 OCR 结果调用 LLM 生成 caption
- [ ] 作为 `image_caption` block 接入现有 chunking pipeline
- [ ] metadata 中标记 `block_type: "image_caption"`

### [ ] E.3.2 表格结构化提取（P2）
**文件：** `app/rag/structured_chunker.py`
**依赖：** `tabby` 或 `camelot`
**操作：**
- [ ] 对 TABLE_LIKE blocks 调用表格结构化解析
- [ ] 输出 JSON 格式（表头、行、列）存储在 metadata
- [ ] 同时保留文本化表示用于检索

### [ ] E.3.3 视频 ASR + Keyframe Caption（P3）
**文件：** 新增 `app/rag/video_processor.py`
**依赖：** `whisper`, `pytesseract`, LLM API
**操作：**
- [ ] ASR 提取音频文本
- [ ] OCR 提取字幕/文字
- [ ] 关键帧 captioning（每隔 N 秒）
- [ ] 时间戳 + 描述作为检索 metadata
- [ ] 文本-first retrieval（用户 query 还是文本）

### [ ] E.3.4 Full Multimodal Embedding（P3）
**文件：** TBD（架构重构）
**依赖：** CLIP 或等效模型
**操作：**
- [ ] 架构设计（超出当前阶段，建议搁置）

---

## 评测相关任务

### [ ] 构建检索评测数据集
**操作：**
- [ ] 人工标注 50-100 个 (query, relevant_chunks) 对
- [ ] 保存为 `tests/evaluation/data/retrieval_benchmark.json`

### [ ] 实现 retrieval 自动化评测
**文件：** `tests/evaluation/test_retrieval.py`
**指标：** Recall@k, MRR@3, NDCG@5

### [ ] 实现 citation 评测
**文件：** `tests/evaluation/test_citation.py`
**指标：** Attribution accuracy, faithfulness rate

### [ ] Chunk 质量抽检
**文件：** `tests/evaluation/test_chunk_quality.py`
**指标：** 句子完整性比例、语义自足比例

---

## 文档任务

### [ ] 更新 `docs/research/rag_research_audit.md`
- [ ] 补充 Phase 0 的具体实现细节（完成后）

### [ ] 补充 `docs/api_contracts.md`
- [ ] 如有新 metadata 字段（parent_id, image_caption 等），更新 API 契约文档
