# 最终 10 条真实体验验收 v3

本文档整理 MindDock 在 Phase 1 / Phase 2A / Phase 2B 改进后的最终体验验收结果。验收方式是 experience-oriented validation：使用少量真实 query 观察 answer、citation、source consistency 和 preview 是否满足答辩演示需求。

这不是大规模 benchmark，也不代表系统完整解决所有 RAG 问题。

2026-04-24 真实前端 / SSE 走查后，最终答辩主流程建议收敛为 H1、N2、Summarize、Source drawer / selected source。TC1 和 Compare 作为 backup / limitation；N1 不作为核心高光。

## 验收目标

- 检查 evidence window 是否让 citation 更完整。
- 检查 citation metadata 是否可验证。
- 检查 section query、local-doc query、structured-ref query 是否比初始版本更稳定。
- 识别仍应作为 limitation / future work 的问题。

## Query 分类

- title / front matter
- heading / section
- table / caption / structured reference
- cross-page continuation
- normal factual / summary

## 汇总表

| ID | Category | Original issue | Fix phase | Current result | Verdict |
|---|---|---|---|---|---|
| TF1 | title/front matter | 标题和主贡献可验证性一般 | Phase 2A-1 / 2B-4 | 能回答标题和主贡献，source 一致 | pass |
| TF2 | title/front matter | abstract 与 experiments 证据可能混合 | Phase 2A-1 | 能识别 abstract evidence 不足，但仍混入 experiments citation | partial |
| H1 | heading/section | Introduction 压过 SYSTEM DESIGN | Phase 2B-1 | top citation 为 `SYSTEM DESIGN · p.3` | pass |
| H2 | heading/section | RELATED WORK 未稳定命中 | 未修 | 仍命中 CONCLUSION / EXPERIMENTS / INTRODUCTION | fail |
| TC1 | structured reference | Table 1 chunk 看不到，后续跨源污染 | Phase 2B-3 / 2B-4 / UI path fix | 前端路径 top citation 可回到 Table 1 引用附近，final citations 保持 Milvus PDF；但 table body 不完整 | partial / backup |
| TC2 | structured reference | Figure 1 未稳定命中 | 未修 | 仍无法定位 Figure 1 内容 | fail |
| CP1 | cross-page | Section 7.1 证据被图表数字污染 | 未修 | section/page 对，但 preview 不可读，answer 保守 | partial |
| CP2 | cross-page | bufferpool 附近证据不完整 | 未修 | 命中 SYSTEM DESIGN 附近，但语义仍不足 | partial |
| N1 | normal factual | 低位 citation 混入 local docs | Phase 2B-4 | 前两条通常来自 Milvus PDF，但低位仍可能混入 `api_usage.md` / `example.md` | partial / not core demo |
| N2 | normal/local docs | local docs query 混入 arxiv PDF | Phase 2B-2 | citations 来自 `rag_pipeline.md` / `architecture.md` | pass |

## 已解决样例

### H1: SYSTEM DESIGN

Query:

```text
What does the SYSTEM DESIGN section of the Milvus paper describe?
```

当前表现：

- top citation: `19_SIGMOD21_Milvus.pdf`
- label: `SYSTEM DESIGN · p.3`
- `hit_in_window = true`
- preview 包含 architecture、query engine、GPU engine、storage engine。

结论：

Phase 2B-1 的 section-aware rerank 生效。

### N2: Local RAG Pipeline

Query:

```text
What are the main steps in the RAG pipeline according to the local docs?
```

当前表现：

- citations: `rag_pipeline.md`、`architecture.md`
- unrelated arxiv PDF 不再进入主要 citations。

结论：

Phase 2B-2 的 local-doc source priority 生效。

### TC1: Table 1

Query:

```text
What differences are summarized in Table 1 of the Milvus paper?
```

当前表现：

- top citation 命中 `19_SIGMOD21_Milvus.pdf:23` 或 Table 1 附近内容。
- final citations 保持在 Milvus PDF。
- `hit_in_window = true`。
- answer 仍会说明 evidence 没有完整 table body。

结论：

Phase 2B-3 解决候选可见性问题，Phase 2B-4 减少低位 source 污染。2026-04-24 UI path fix 后，frontend unified path 与 CLI smoke 不再因为 precomputed hits 跳过 structured-ref injection 而明显不一致。但该 query 更适合作为 backup / limitation：系统能定位 Table 1 引用附近，完整表格对象级抽取仍是 future work。

### N1: What is Milvus?

Query:

```text
What is Milvus?
```

当前表现：

- 前两条 citations 通常来自 Milvus PDF。
- 低位 citation 仍可能混入 `api_usage.md` / `example.md`。

结论：

Phase 2B-4 的 source consistency cap 对排序有帮助，但普通开放实体 query 仍有 source consistency 边界。该 query 不建议作为核心高光 demo。

### Summarize: Milvus system design

Query:

```text
Summarize Milvus system design
```

当前表现：

- summary 可读。
- citations 稳定来自 Milvus SYSTEM DESIGN 相关内容。
- citation label 和 evidence preview 在真实 UI 中可见。

结论：

适合作为核心演示，展示 summarize 复用 retrieval / citation 链路。

### Compare: Milvus vs local RAG pipeline

Query:

```text
Compare Milvus and the local RAG pipeline
```

当前表现：

- 能正常返回 structured compare artifact。
- UI 不再重复展示 text artifact 和 structured artifact 两份主结果。
- 内容仍偏泛。

结论：

适合作为 backup 展示“能跑通”，不作为质量亮点。

## 未解决 / Limitation

### H2: RELATED WORK

Query:

```text
What does the RELATED WORK section of the Milvus paper discuss?
```

当前问题：

- 仍可能命中 CONCLUSION、EXPERIMENTS 或 INTRODUCTION。

可能原因：

- section query 意图更复杂。
- 正确 section 候选可能仍未进入可见范围。
- 需要更强 metadata-aware rerank 或 query rewrite。

### TC2: Figure 1

Query:

```text
What does Figure 1 in the Milvus paper show?
```

当前问题：

- 仍不能稳定命中 Figure 1 对应上下文。

可能原因：

- figure/caption extraction 不足。
- PDF parser 尚未建立 figure/table object-level metadata。
- 可能需要 layout-aware parser、caption graph 或 multimodal 支持。

### CP1 / CP2: Cross-page and Layout Noise

当前问题：

- Section/page 可能正确，但 evidence preview 中有图表数字污染。
- 跨页段落和图表附近文本清洗仍不充分。

可能方向：

- 更强跨页段落合并。
- layout-aware cleaning。
- 更细粒度 block type 和 figure/table 绑定。

### doc_type / source_kind

当前问题：

- local-doc priority 和 source consistency 仍主要依赖 source string、extension 和启发式规则。

未来方向：

- 在 ingest 阶段正式写入 `doc_type` / `source_kind` / `origin` metadata。

## 结论

当前阶段可以收口。Phase 1 / Phase 2A / Phase 2B 已经形成完整的体验驱动修复链：

1. hit-preserving evidence window
2. verifiable citation metadata
3. section-aware rerank
4. local-doc source priority
5. structured-ref lexical injection
6. source consistency cap

后续工作应集中在 parser/layout/source metadata/formal eval，而不是继续堆小型 heuristic。
