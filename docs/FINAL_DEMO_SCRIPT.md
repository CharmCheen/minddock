# MindDock 最终答辩演示脚本

本文档给出固定演示脚本，适合答辩现场按顺序执行。目标是展示系统闭环和 RAG citation/retrieval 改进效果，而不是现场探索未知问题。

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

如果需要 CLI 验证：

```powershell
python -m app.demo sources
```

## 1. H1: Section-aware Rerank

Query:

```text
What does the SYSTEM DESIGN section of the Milvus paper describe?
```

演示目的：

- 展示 section-aware rerank。
- 展示 citation label 和 evidence preview。

操作步骤：

1. 在 chat 输入 query。
2. 查看 answer。
3. 展开 Sources 区域。

预期现象：

- top citation 为 `19_SIGMOD21_Milvus.pdf`。
- `citation_label` 类似 `SYSTEM DESIGN · p.3`。
- preview 包含 Milvus architecture、query engine、GPU engine、storage engine。
- `Hit in window` 为 true。

关键观察点：

- 原来 Introduction 容易压过 SYSTEM DESIGN。
- 现在 query 明确提到 section 时，正确 section 能稳定排到前面。

失败备用说法：

- 如果没有命中 SYSTEM DESIGN，说明 section-aware rerank 仍有边界，需要进一步 metadata-aware rerank 或 query rewrite。

## 2. N2: Local-doc Source Priority

Query:

```text
What are the main steps in the RAG pipeline according to the local docs?
```

演示目的：

- 展示 local-doc source priority。
- 展示 source scope / source consistency 对可信引用的作用。

预期现象：

- citations 来自 `rag_pipeline.md`、`architecture.md` 等本地 Markdown。
- 不应混入 unrelated arxiv PDF。
- answer 应列出 ingest、chunking、embedding、vector database、retrieval 等步骤。

关键观察点：

- query 中的 `according to the local docs` 会触发本地文档优先策略。
- 该策略不覆盖显式 source filters。

失败备用说法：

- 如果混入论文 PDF，说明 source/domain policy 仍需正式 `doc_type/source_kind` metadata。

## 3. TC1: Structured-ref Lexical Injection

Query:

```text
What differences are summarized in Table 1 of the Milvus paper?
```

演示目的：

- 展示 Table/Figure 编号 query 的 lexical injection。
- 展示 source consistency cap。

预期现象：

- top citation 命中 `19_SIGMOD21_Milvus.pdf:23` 或 Table 1 附近内容。
- `hit_in_window == true`。
- final citations 保持在 Milvus PDF。
- answer 会说明 evidence 没有完整 table body，但能定位到 Table 1 相关上下文。

关键观察点：

- 原问题是 BM25 能找到 Table 1，但 dense candidate pool 太浅，chat rerank 看不到。
- 当前通过窄触发 lexical candidate 注入解决候选可见性问题。

失败备用说法：

- 如果 table body 仍不完整，这是 parser/table object-level metadata 的后续工作，不是 citation pipeline 失败。

## 4. N1: Source Consistency

Query:

```text
What is Milvus?
```

演示目的：

- 展示普通单实体 query 下，低位 citation 不再混入无关 local docs。

预期现象：

- citations 主要来自 `19_SIGMOD21_Milvus.pdf`。
- citation label 包含 `Abstract · p.1` 或 `SYSTEM DESIGN · p.3`。
- answer 是 grounded answer，不是开放聊天。

失败备用说法：

- 如果低位混入其他 source，说明 source consistency cap 仍需更正式的 source_kind 支撑。

## 5. Summarize

CLI:

```powershell
python -m app.demo summarize --topic "Milvus system design" --top-k 4
```

演示目的：

- 展示摘要任务复用 retrieval / citation pipeline。

预期现象：

- 输出 summary。
- citations 中包含 source、section、label、preview。

失败备用说法：

- 如果 LLM key 不可用，系统可能走 mock fallback；可说明这不影响检索与 citation 链路演示。

## 6. Compare

CLI:

```powershell
python -m app.demo compare --question "Compare the Milvus paper with the local RAG pipeline docs." --top-k 4
```

演示目的：

- 展示跨文档任务。
- 展示 source consistency 不会把 compare query 强行单源化。

预期现象：

- citations 至少包含 Milvus PDF 和 local docs。
- answer 以对比形式组织。

失败备用说法：

- 如果混入额外论文，可说明 compare 是跨源任务，当前仍依赖 rerank 质量，未来可加入 doc_type/source_kind。

## 7. Optional: Source Drawer

操作：

1. 点击任一 citation。
2. 打开 source drawer。
3. 查看 source detail 和 chunk previews。

演示目的：

- 展示用户可以追踪答案来源。

已知限制：

- 当前 source drawer 尚未完整展开 evidence window。
- 完整 evidence window 高亮可作为后续 UI 工作。

## 8. 现场避免事项

- 不临时问复杂 Figure 1 / caption / table body 问题。
- 不临时问跨页图表数字密集内容。
- 不现场切换模型或重建大索引。
- 不删除或重入库核心 demo source。
