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

真实前端走查后的稳定主线是：H1、N2、Summarize、Source drawer / selected source。TC1 和 Compare 可以作为 backup；N1 不建议作为核心高光。

答辩调试或讲解 pipeline 时，可以在 CLI 里加 `--trace`：

```powershell
python -m app.demo chat --query "What does the SYSTEM DESIGN section of the Milvus paper describe?" --trace
```

Trace 只展示结构化 workflow metadata，例如 mode、requested top_k、内部 candidate pool、source scope、已触发的 deterministic rules 和最终 source 摘要。它不改变回答结果，不暴露模型隐藏推理，也不记录完整 prompt 或长 chunk 文本。

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

### 4. Summarize

Query:

```text
Summarize Milvus system design
```

展示点：

- summarize 与 chat 复用同一 retrieval / citation 链路。
- summary 也有 citation label 和 evidence preview。
- source 稳定在 Milvus system design 相关内容。

### 5. Source Drawer

操作：

- 点击 source 列表或 citation 旁的 source detail 入口。
- 展示 selected source / source scope 状态。
- 查看 source detail 和 chunk preview。

展示点：

- source catalog 和 source scope 能帮助用户理解当前检索范围。
- chunk preview 能帮助用户检查回答来源。
- 当前 drawer 尚未完整展开 evidence window，这是后续工作。

## Backup / Limitation 演示

## Sync-once / Watch Demo

This is optional for Phase 3A. Use it when you want to show that MindDock can keep the local `knowledge_base` aligned without a full rebuild.

Dry-run preview:

```powershell
conda run --no-capture-output -n minddock python -m app.demo watch --once --dry-run
```

Add a small Markdown file under `knowledge_base`, then run:

```powershell
conda run --no-capture-output -n minddock python -m app.demo watch --once
conda run --no-capture-output -n minddock python -m app.demo sources
```

Modify the same file and run `watch --once` again. The source should stay single and the chunks should be replaced rather than duplicated. Delete the file and run `watch --once`; the source should disappear because the matching Chroma chunks and HashStore entry are removed.

Continuous watch mode:

```powershell
conda run --no-capture-output -n minddock python -m app.demo watch --path knowledge_base --debounce 2.0
```

On Windows, avoid syncing while a large file is still being copied. Use `--once --dry-run` first when the file write state is uncertain.

## Image OCR Source Demo

Phase 3D adds image-to-text ingest for `.png`, `.jpg`, `.jpeg`, and `.webp` files in `knowledge_base/`.
This is not full multimodal RAG: the system extracts OCR text from an image and indexes that text through the existing text chunking, Chroma, retrieval, and citation path.

Default demo behavior uses mock OCR. The mock OCR output only proves that image sources can enter the ingest and retrieval pipeline; it does not claim to read or understand the real image. RapidOCR can be used as an optional provider when installed and configured with `IMAGE_OCR_PROVIDER=rapidocr`. RapidOCR is not a required dependency, and missing RapidOCR should fall back safely instead of breaking normal ingest.

Useful CLI flow:

```powershell
conda run --no-capture-output -n minddock python -m app.demo watch --once --dry-run
conda run --no-capture-output -n minddock python -m app.demo watch --once
conda run --no-capture-output -n minddock python -m app.demo sources
conda run --no-capture-output -n minddock python -m app.demo chat --query "What does sample_image.png contain?"
```

Expected metadata for indexed image chunks includes `source_media=image`, `source_kind=image_file`, `loader_name=image.ocr`, `ocr_provider`, `retrieval_basis=ocr_text`, and `image_filename`.

Do not present this as image captioning, PDF figure extraction, frontend image preview, video/audio support, OCR table reconstruction, or multimodal embedding.

### A. Structured Reference Query: Table 1

Query:

```text
What differences are summarized in Table 1 of the Milvus paper?
```

展示点：

- top citation 应命中 `19_SIGMOD21_Milvus.pdf:23` 或 Table 1 附近内容。
- final citations 应保持在 Milvus PDF 内。
- 展示 structured-ref lexical injection 和 source consistency cap。
- 主动说明完整 table body / object-level extraction 仍是 future work。

### B. Compare

Query:

```text
Compare Milvus and the local RAG pipeline
```

展示点：

- compare 是独立任务类型。
- UI 不再同时展示 text artifact 和 structured artifact 两份主结果。
- 作为能跑通的备用流程，不作为质量亮点。

### C. Normal Query: What is Milvus?

Query:

```text
What is Milvus?
```

展示点：

- 前两条通常来自 Milvus PDF。
- 低位 citation 仍可能混入 local docs。
- 不建议作为核心演示；用于说明普通开放 query 的 source consistency 仍有局限。

## 备用说明

如果遇到 Figure 1、Table body、cross-page 问题，可以说明：

- 当前阶段重点是 answer grounding 与 citation 可验证性。
- Figure/table object-level parsing、跨页段落合并、layout-aware cleaning 属于 future work。
- 相关 limitation 已在最终验收报告中记录。
- TC1 已能定位 Table 1 引用附近，但完整表格对象级内容抽取仍是 future work。
- N1 这类普通开放实体 query 不作为核心高光，source consistency 仍需更正式的 source metadata 支撑。

## 不建议现场临时尝试

- 不建议现场随机问复杂 Figure/caption 问题。
- 不建议现场重建大索引，除非已经确认时间充足。
- 不建议现场切换 embedding 或 LLM provider。
- 不建议现场删除/重入库重要 source。
