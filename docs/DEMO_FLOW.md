# MindDock 最终演示流程

本文档给出毕业设计答辩时的推荐演示顺序和备用方案。目标是展示系统闭环和 RAG citation/retrieval 改进效果，而不是现场探索未知问题。

## 演示前准备

后端启动：

```powershell
conda activate minddock
python -m app.demo serve
```

前端启动：

```powershell
cd frontend
npm run dev
```

浏览器打开：

```text
http://localhost:5173
http://127.0.0.1:8000/docs
```

确认 source 可用：

```powershell
python -m app.demo sources
```

## 核心演示（必须展示）

### H1: Section-aware Rerank

**Query:**

```text
What does the SYSTEM DESIGN section of the Milvus paper describe?
```

**展示点：**

- top citation 应为 `SYSTEM DESIGN · p.3`
- 展示 section-aware rerank
- citation 中有 `hit_in_window`、`window_chunk_count`、`evidence_preview`

**失败备用说法：**

- 如果没有命中 SYSTEM DESIGN，说明 section-aware rerank 仍有边界，需要进一步 metadata-aware rerank 或 query rewrite。

---

### N2: Local-doc Source Priority

**Query:**

```text
What are the main steps in the RAG pipeline according to the local docs?
```

**展示点：**

- citations 应来自 `rag_pipeline.md` / `architecture.md`
- 展示 local-doc source priority
- 说明 query 明确说 local docs 时，系统会避免无关论文 PDF 混入主 citations

**失败备用说法：**

- 如果混入论文 PDF，说明 source/domain policy 仍需正式 `doc_type/source_kind` metadata。

---

### Watchdog Sync-once

**操作：**

1. 在 `knowledge_base/` 下新建一个小的 Markdown 文件，例如 `demo_sync.md`
2. 运行 `watch --once`：

```powershell
conda run --no-capture-output -n minddock python -m app.demo watch --once
```

3. 运行 `sources` 确认新文件已入库
4. 修改该文件再运行一次 `watch --once`，确认 source 保持单一、chunks 被替换而非重复
5. 删除该文件再运行一次 `watch --once`，确认 source 消失

**展示点：**

- 增量增删改，无需 rebuild
- dry-run 可预览变更

---

### Source Drawer / Citation

**操作：**

- 在 chat 回答中点击任意 citation
- 或打开前端 source 列表，点击 source detail

**展示点：**

- source catalog 和 source scope 帮助用户理解当前检索范围
- chunk preview 帮助用户检查回答来源
- evidence window 保证 `hit_in_window == true`

---

### Workflow Trace

**操作：**

CLI 中加 `--trace`：

```powershell
python -m app.demo chat --query "What does the SYSTEM DESIGN section of the Milvus paper describe?" --trace
```

**展示点：**

- 展示结构化 pipeline metadata：`requested_top_k`、`internal_candidate_k`、`applied_rules`、`final_sources`
- 说明 trace 不改变回答结果，不暴露模型隐藏推理，不记录完整 prompt

---

## Backup 演示（可选展示）

### URL Static HTML Source

如果知识库中已有 URL source，可展示其 metadata：`source_media=text`、`source_kind=web_page`、`loader_name=url.extract`。

主动说明：URL 只支持 static HTML，不支持 JS 渲染、登录态、反爬。

### Image OCR Source

如果知识库中已有 image source，可展示其 metadata：`source_media=image`、`source_kind=image_file`、`loader_name=image.ocr`、`retrieval_basis=ocr_text`。

主动说明：这是 OCR-first 路径，不是 image caption，也不是 multimodal RAG。

### CSV Source Skill

如果知识库中已有 CSV source，可展示 `source_kind=csv_file`、`loader_name=csv.extract`、`csv_columns`、`csv_row_count`。

主动说明：CSV 只做行转文本，不做 Excel/表格推理。

### TC1: Structured-ref Lexical Injection

**Query:**

```text
What differences are summarized in Table 1 of the Milvus paper?
```

**定位：**

- 不作为核心高光
- 用于展示 limitation 更稳：系统能定位 Table 1 引用附近，但完整 table body 仍是 future work

### Compare

**Query:**

```text
Compare Milvus and the local RAG pipeline
```

**定位：**

- 作为“能跑通”的跨文档任务类型展示
- 不作为质量亮点

---

## 不建议现场展示

以下 query 或功能不建议作为答辩核心高光：

- **大文档 full summarize** — 容易触发 context truncation，不是 summarize 的强项
- **长截图 OCR 总结** — OCR 质量不可控
- **动态网页 / 飞书 / Notion URL** — URL loader 不支持 JS 渲染
- **音频 / 视频** — transcript trusted handler P0 已实现，默认使用 mock provider；真实 ASR / 视频理解仍是 future work。现场可作为架构扩展示例展示，但必须说明是 mock placeholder
- **image caption** — 未实现，当前是 OCR text 路径
- **复杂 Table/Figure object-level QA** — parser 不完整
- **N1 类普通开放 query** — source consistency 仍有边界，容易混入无关 source

---

## 备用说明

如果遇到 Figure 1、Table body、cross-page 问题，可以说明：

- 当前阶段重点是 answer grounding 和 citation 可验证性
- Figure/table object-level parsing、跨页段落、layout-aware cleaning 属于 future work
- 相关 limitation 已在最终验收报告中记录
