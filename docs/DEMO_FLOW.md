# MindDock 最终答辩演示流程

本文档用于答辩现场的演示彩排。详细逐句脚本见 [FINAL_DEMO_SCRIPT.md](FINAL_DEMO_SCRIPT.md)，最终 10 条体验验收见 [FINAL_VALIDATION_V3.md](FINAL_VALIDATION_V3.md)。

## 演示目标

展示 MindDock 已形成一个可运行的个人知识库 RAG 系统闭环：

1. 文档导入与索引
2. 检索与问答
3. grounded answer
4. 可验证 citation
5. source catalog / source drawer
6. source scope
7. 摘要与对比

## 演示前准备

建议提前完成：

```powershell
conda activate minddock
python -m app.demo ingest
```

确认 source 可用：

```powershell
python -m app.demo sources
```

启动后端：

```powershell
python -m app.demo serve
```

启动前端：

```powershell
cd frontend
npm run dev
```

浏览器打开：

```text
http://localhost:5173
```

## 推荐演示顺序

### 1. Source Catalog

操作：

- 打开前端 source 列表，或运行：

```powershell
python -m app.demo sources
```

说明：

- 系统已索引 PDF、Markdown 等多种来源。
- source 是 citation 和 filter 的稳定身份。

### 2. Section Query: SYSTEM DESIGN

Query:

```text
What does the SYSTEM DESIGN section of the Milvus paper describe?
```

展示点：

- top citation 应为 `SYSTEM DESIGN · p.3`。
- 展示 section-aware rerank。
- citation 中有 `hit_in_window`、`window_chunk_count`、`evidence_preview`。

### 3. Local Docs Query

Query:

```text
What are the main steps in the RAG pipeline according to the local docs?
```

展示点：

- citations 应来自 `rag_pipeline.md` / `architecture.md`。
- 展示 local-doc source priority。
- 说明 query 明确说 local docs 时，系统会避免无关论文混入主要 citations。

### 4. Structured Reference Query: Table 1

Query:

```text
What differences are summarized in Table 1 of the Milvus paper?
```

展示点：

- top citation 应命中 `19_SIGMOD21_Milvus.pdf:23` 或 Table 1 附近内容。
- final citations 应保持在 Milvus PDF 内。
- 展示 structured-ref lexical injection 和 source consistency cap。

### 5. Normal Query: What is Milvus?

Query:

```text
What is Milvus?
```

展示点：

- answer 来自 Milvus PDF。
- 低位 citation 不再混入 local docs。
- 展示 source consistency cap 对普通单实体 query 的效果。

### 6. Summarize

CLI:

```powershell
python -m app.demo summarize --topic "Milvus system design" --top-k 4
```

展示点：

- summarize 与 chat 复用同一 retrieval / citation 链路。
- summary 也有 citations。

### 7. Compare

CLI:

```powershell
python -m app.demo compare --question "Compare the Milvus paper with the local RAG pipeline docs." --top-k 4
```

展示点：

- compare 是独立任务类型。
- 系统不会把明确跨文档 query 强行单源化。

### 8. Source Drawer

操作：

- 点击 citation。
- 打开 source drawer。

展示点：

- source detail 和 chunk preview 能帮助用户检查回答来源。
- 当前 drawer 尚未完整展开 evidence window，这是后续工作。

## 备用说明

如果遇到 Figure 1、Table body、cross-page 问题，可以说明：

- 当前阶段重点是 answer grounding 与 citation 可验证性。
- Figure/table object-level parsing、跨页段落合并、layout-aware cleaning 属于 future work。
- 相关 limitation 已在最终验收报告中记录。

## 不建议现场临时尝试

- 不建议现场随机问复杂 Figure/caption 问题。
- 不建议现场重建大索引，除非已经确认时间充足。
- 不建议现场切换 embedding 或 LLM provider。
- 不建议现场删除/重入库重要 source。
