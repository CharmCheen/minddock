# 第三阶段汇报提纲（精简版）

**汇报日期：2026-04-19**

---

## 一、五项核心成果

### 成果 1：结构化分块与证据链
- 修复页边界 flush 导致的跨页段落合并问题
- PDF section_path 覆盖率：83%–98%，16/16 文档重建成功
- chunking 评测（Structured+Hybrid+SoftV3）：
  - page_hit@1 = **0.667**，page_hit@5 = 0.944
  - section_hit@1 = 0.611，bt_hit@1 = 0.833
  - mrr_page = 0.759，mrr_section = 0.690
- Page-Mode 基线（无 rerank）全部指标为 0，改进真实有效

### 成果 2：证据锚定与参与状态
- 新增 EvidenceItem：highlighted_sentence + position_start/end + block_id + section_path
- participation_state 后端投影：cited / revisited / copied 全链路打通
- 前端 citation revisit 和 participation overlay 已上线

### 成果 3：Metadata-Aware Rerank
- AUTHOR / REFERENCE 区域降权 -0.15，ABSTRACT 降权 -0.05
- 显式 intent 查询（author/abstract/references）可 bypass 降权
- 主链无回归，评测通过

### 成果 4：Re-ingest 安全迁移
- scripts/reingest_metadata.py 支持备份 + 原子化重建 + 验证
- 16/16 文档全量迁移成功，section_path / semantic_type 正式进入 retrieval pipeline
- 迁移过程零数据丢失

### 成果 5：Benchmark 修订 + Compare Dual Retrieval
- 评测指标修订：hit@1 = **75%**，hit@3 = **85%**，hit@5 = **95%**（v2）
- 6 项标注错误修正，评测口径与真实用户查询对齐
- Compare dual retrieval 修复 compare_agentic_rag_vs_milvus，多主题联合查询不再失效

---

## 二、剩余局限（诚实列出）

1. **Compare topic diversity 失效**：`compare_architecture_md` 因内部文档内容重叠，两个子查询召回相同 doc_id，topic diversity 机制无法生效，属于文档层面的系统限制

2. **Markdown 文档覆盖率偏低**：目前只有 PDF 走 structured chunker，markdown 文档的 section_path / semantic_type 元数据仍不完整

3. **Compare LLM 引用偏差**：3 个 compare case 检索命中但 LLM 选择了不同源，这是生成侧问题，非检索侧能解决

4. **降权幅度未系统调参**：-0.15 / -0.05 是经验值，在不同文档集上效果可能有波动

5. **评测集规模有限**：统计置信度未做系统验证，不宜过度解读小数点差异

---

## 三、下一步（如需继续推进）

### 短期
- 解决 compare 场景下内部文档内容重叠导致的 topic diversity 失效
- 对 metadata rerank 降权参数做系统化调参

### 中期（毕业答辩前）
- 端到端 compare 流程演示验证
- 补充 markdown 文档的 structured chunking 支持
- 扩大评测集规模，提升统计置信度

### 长期（如有后续）
- 跨页段落重建算法优化（减少启发式依赖）
- 表格/公式语义块识别
- citation 引用准确性的生成侧优化

---

*数据来源：eval/chunking_eval_report_v4.md、data/eval/pdf_benchmark_revision_notes.md、scripts/reingest_metadata.py、git commits*
