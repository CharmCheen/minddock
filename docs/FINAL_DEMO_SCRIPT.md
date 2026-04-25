# MindDock 最终答辩演示脚本

本文档给出固定演示脚本，适合答辩现场按顺序执行。目标是展示系统闭环和 RAG citation/retrieval 改进效果。

最新前端走查后的稳定主线：

- **核心演示**：H1、N2、Watchdog、Source drawer、Workflow trace
- **可选 / backup**：URL、Image OCR、CSV、TC1、Compare
- **不建议核心高光**：N1

## 0. 启动检查

后端：

```powershell
conda activate minddock
python -m app.demo serve
```

前端：

```powershell
cd frontend
npm run dev
```

打开：

```text
http://localhost:5173
http://127.0.0.1:8000/docs
```

如需 CLI 验证：

```powershell
python -m app.demo sources
```

---

## 1. H1: Section-aware Rerank

**Query:**

```text
What does the SYSTEM DESIGN section of the Milvus paper describe?
```

**演示目的：**

- 展示 section-aware rerank
- 展示 citation label 和 evidence preview

**操作步骤：**

1. 在 chat 输入 query
2. 查看 answer
3. 展开 Sources 区域

**预期现象：**

- top citation 为 `19_SIGMOD21_Milvus.pdf`
- `citation_label` 类似 `SYSTEM DESIGN · p.3`
- preview 包含 Milvus architecture、query engine、GPU engine、storage engine
- `Hit in window` 为 true

**关键观察点：**

- 原来 Introduction 容易压过 SYSTEM DESIGN
- 现在 query 明确提到 section 时，正确 section 能稳定排到前面

**失败备用说法：**

- 如果没有命中 SYSTEM DESIGN，说明 section-aware rerank 仍有边界，需要进一步 metadata-aware rerank 或 query rewrite。

---

## 2. N2: Local-doc Source Priority

**Query:**

```text
What are the main steps in the RAG pipeline according to the local docs?
```

**演示目的：**

- 展示 local-doc source priority
- 展示 source scope / source consistency 对可信引用的作用

**预期现象：**

- citations 来自 `rag_pipeline.md`、`architecture.md` 等本地 Markdown
- 不应混入 unrelated arxiv PDF
- answer 应列出 ingest、chunking、embedding、vector database、retrieval 等步骤

**关键观察点：**

- query 中的 `according to the local docs` 会触发本地文档优先策略
- 该策略不覆盖显式 source filters

**失败备用说法：**

- 如果混入论文 PDF，说明 source/domain policy 仍需正式 `doc_type/source_kind` metadata。

---

## 3. Watchdog Sync-once

**操作：**

1. 在 `knowledge_base/` 下新建 `demo_sync.md`，写入几行内容
2. 运行：

```powershell
conda run --no-capture-output -n minddock python -m app.demo watch --once
```

3. 运行 `sources` 确认已入库
4. 修改 `demo_sync.md` 内容，再次运行 `watch --once`
5. 删除 `demo_sync.md`，再次运行 `watch --once`
6. 运行 `sources` 确认已移除

**演示目的：**

- 展示基于内容哈希的增量同步
- 增删改无需 rebuild

**预期现象：**

- 新增：created | updated
- 修改：modified | updated，chunks 被替换而非重复
- 删除：deleted | removed

---

## 4. Source Drawer / Citation

**操作：**

- 在 chat 回答中点击任意 citation
- 或打开前端 source 列表，点击 source detail

**演示目的：**

- 展示用户可以追溯答案来源

**展示点：**

- source catalog 和 source scope 帮助用户理解当前检索范围
- chunk preview 帮助用户检查回答来源
- evidence window 保证 `hit_in_window == true`

**已知限制：**

- 当前 source drawer 尚未完整展开 evidence window
- 完整 evidence window 高亮可作为后续 UI 工作

---

## 5. Workflow Trace

**操作：**

CLI 中加 `--trace`：

```powershell
python -m app.demo chat --query "What does the SYSTEM DESIGN section of the Milvus paper describe?" --trace
```

**演示目的：**

- 展示回答背后的 pipeline 可观测性

**展示点：**

- `requested_top_k`、内部 `internal_candidate_k`
- `applied_rules`：如 `evidence_window`、`source_consistency_cap`
- `final_sources`：最终使用了哪些 source
- `trace_warnings`：如有 mixed_sources 等提示

**关键说明：**

- trace 只展示结构化 workflow metadata
- 不改变回答结果，不暴露模型隐藏推理，不记录完整 prompt 或长 chunk 文本

---

## Backup / Limitation 演示

### TC1: Structured-ref Lexical Injection

**Query:**

```text
What differences are summarized in Table 1 of the Milvus paper?
```

**定位：**

- 不作为核心高光
- 用于展示 limitation 更稳

**预期现象：**

- top citation 命中 `19_SIGMOD21_Milvus.pdf:23` 或 Table 1 附近内容
- `hit_in_window == true`
- final citations 保持在 Milvus PDF 内

**主动说明：**

- 系统能定位 Table 1 引用附近，但完整 table body 仍是 future work
- 展示 structured-ref lexical injection 和 source consistency cap

**失败备用说法：**

- 如果 table body 仍不完整，这是 parser/table object-level metadata 的后续工作，不是 citation pipeline 失败。

---

### CSV Source Skill（可选）

如果知识库中已有 CSV，可展示：

```powershell
python -m app.demo source-detail --source student_projects.csv
```

**展示点：**

- `source_kind=csv_file`
- `loader_name=csv.extract`
- `csv_columns`、`csv_row_count`

**主动说明：**

- CSV 通过 Source Skill Contract 接入，新增 source skill 无需改 retrieval/citation/frontend

---

### Compare（可选）

**Query:**

```text
Compare Milvus and the local RAG pipeline
```

**定位：**

- 作为“能跑通”的跨文档任务类型展示
- 不作为质量亮点

---

## 现场避免事项

- 不临时问复杂 Figure 1 / caption / table body 问题
- 不现场问跨页图表数字密集内容
- 不现场切换模型或重建大索引
- 不删除或重入库核心 demo source
- 不展示 URL source 作为核心高光（只作为 backup）
- 不展示 Image OCR 作为核心高光（只作为 backup）
- 不展示 N1 类普通开放 query 作为核心高光
