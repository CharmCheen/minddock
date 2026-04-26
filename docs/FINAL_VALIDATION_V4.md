# MindDock 最终验收报告 V4

## 验收范围

本报告验收 MindDock 毕业设计最终版本的功能完整性、稳定性和演示就绪度。

**验收分支：** `docs/final-demo-thesis-materials`（已 fast-forward 到最新 master）  
**验收日期：** 2026-04-25  
**验收方式：** 单元测试 + CLI smoke + 前端走查 + 真实体验 query

---

## 环境与分支状态

- **Python：** 3.11
- **Conda env：** minddock
- **本地 master：** `4d4af3f` Merge pull request #11
- **origin/master：** `4d4af3f`（已同步）
- **工作树：** clean
- **核心回归：** 229 passed, 23 warnings

---

## 测试结果摘要

| 测试套 | 结果 |
|---|---|
| Import smoke | ✅ passed |
| Source skill catalog focused | 19 passed |
| CSV loader focused | 14 passed |
| Incremental ingest + CSV | 52 passed (focused) |
| Source loader related regression | 83 passed |
| Core regression (全部 unit) | 229 passed, 23 warnings |
| Manual CSV smoke | ✅ passed（dry-run / ingest / search / chat / delete） |
| Frontend build | ✅ passed |

---

## 功能分级

### A. Core demo ready（答辩核心展示）

| 功能 | 状态 | 说明 |
|---|---|---|
| PDF RAG 问答 | ✅ 稳定 | Structured PDF chunking + citation page support |
| Local docs 问答 | ✅ 稳定 | Markdown/TXT ingest，local-doc priority |
| Citation / Evidence window | ✅ 稳定 | `hit_in_window`、`window_chunk_count`、`evidence_preview` |
| Source drawer | ✅ 稳定 | Source list、detail、chunk preview |
| Watchdog sync-once | ✅ 稳定 | Hash-based incremental add/modify/delete + dry-run |
| Workflow trace | ✅ 稳定 | Structured metadata：applied_rules、candidate counts、final sources |
| Section-aware rerank | ✅ 稳定 | `SYSTEM DESIGN section` 可稳定优先命中 |
| Structured-ref lexical injection | ✅ 稳定 | `Table 1`、`Fig. 2` 窄触发 BM25 + 回查注入 |
| Source consistency cap | ✅ 稳定 | 高置信单源场景减少 unrelated citation |

### B. Usable with caveats（可用，但需主动说明限制）

| 功能 | 状态 | 说明 |
|---|---|---|
| URL source | ✅ 可用 | 仅 static HTML，不支持 JS 渲染、登录态、反爬 |
| Image OCR | ✅ 可用 | mock fallback 默认，RapidOCR 可选；不是 image caption |
| CSV source skill | ✅ 可用 | 标准库 csv 解析，行转文本；不支持 Excel/表格推理 |
| Compare | ✅ 可用 | 跨文档对比，能跑通，不作为质量亮点 |
| Summarize 小文档 | ✅ 可用 | 复用 retrieval/citation 链路；大文档有 context safety guard |

### C. Technical path works but UX weak（技术路径通，体验不够完整）

| 功能 | 状态 | 说明 |
|---|---|---|
| Long screenshot OCR summary | ⚠️ 弱 | OCR 质量不可控，长图容易截断 |
| Structured table/figure QA | ⚠️ 弱 | 能定位 Table 1 附近，但没有完整 table body extraction |
| General query source consistency | ⚠️ 弱 | N1 类开放 query 仍可能混入无关 source |

### D. Future work（未实现，只作为扩展方向）

| 功能 | 状态 | 说明 |
|---|---|---|
| Audio / video transcription | ❌ 未实现 | Source Skill Contract 已预留 audio.transcribe / video.transcribe |
| Image caption | ❌ 未实现 | Source Skill Contract 已预留 image.caption |
| Multimodal embedding | ❌ 未实现 | 当前是 text embedding + OCR text 路径 |
| JS-rendered URL | ❌ 未实现 | 需要 headless browser |
| Full Agent Skill Runtime | ❌ 未实现 | 当前是 deterministic source skill，不是 LLM 自主调用 |
| Complex table/figure object-level QA | ❌ 未实现 | 需要完整 parser + metadata 支撑 |

---

## 真实体验验收总结

### 核心 demo 推荐流程

1. **H1: Section Query** — `What does the SYSTEM DESIGN section of the Milvus paper describe?`  
   → top citation 稳定在 `SYSTEM DESIGN · p.3`，展示 section-aware rerank

2. **N2: Local Docs** — `What are the main steps in the RAG pipeline according to the local docs?`  
   → citations 来自本地 Markdown，展示 local-doc priority

3. **Watchdog sync-once** — 新增/修改/删除文件，验证增量同步

4. **Source Drawer** — 点击 citation 追溯来源，展示 evidence window

5. **Workflow Trace** — `--trace` 展示 pipeline 结构化 metadata

### Backup demo 推荐

- **URL source** — 展示 `source_media=text`、`source_kind=web_page`、`loader_name=url.extract`
- **Image OCR** — 展示 `source_media=image`、`loader_name=image.ocr`、`retrieval_basis=ocr_text`
- **CSV source skill** — 展示 `source_kind=csv_file`、`loader_name=csv.extract`，验证 Source Skill Contract 扩展路径
- **TC1: Table 1 query** — 展示 structured-ref lexical injection，同时主动说明 table body 不完整
- **Compare** — 展示跨文档任务能跑通

### Limitations（答辩时应主动说明）

- URL 只支持 static HTML，不支持动态网页
- Image OCR 是 OCR text 路径，不是 image caption / multimodal RAG
- CSV 只做行转文本，不支持 Excel / 表格推理
- Figure/table object-level parsing 不完整
- Cross-page evidence 和 layout cleaning 仍需增强
- Rerank 是 heuristic，不是 cross-encoder
- Context compression 是 trimming，不是 LLM compression

### Post-V4 Update / Latest Status

After PR #18 (merged to master), `audio.transcribe` and `video.transcribe` are implemented as transcript-only trusted handlers with mock provider by default. They validate the Source Skill / Trusted Handler extension path, while real ASR, full video understanding, multimodal embedding, timestamp citation UI, and player UI remain future work.

### Future work（答辩时可提及）

- Real ASR provider for audio/video transcription
- Image caption via multimodal model
- JS-rendered URL via headless browser
- Full Agent Skill Runtime（当前是 deterministic contract）

---

## Source Skill Contract 验证

**已实现的 source skills（active catalog）：**

- `file.pdf` — pdf.parse
- `file.markdown` — markdown.read
- `file.text` — text.read
- `url.extract` — static HTML extraction
- `image.ocr` — OCR text with optional RapidOCR
- `csv.extract` — CSV rows as text

**验证方式：**

- `csv.extract` 作为新 source skill 独立实现于 `app/rag/source_skills/csv_skill.py`
- 注册到 `SourceLoaderRegistry` 后，现有 RAG pipeline（chunking / embedding / retrieval / citation）无需任何修改即可使用
- 证明 Source Skill Contract 的扩展路径有效

**Future skills（仅文档，不进 active catalog）：**

- `image.caption`
- `audio.transcribe`
- `video.transcribe`
- `url.js_rendered`

---

## 最终结论

项目已经达到毕业设计可交付标准。

**已形成稳定闭环的能力：**

- PDF / Markdown / TXT 结构化解析与入库
- 向量检索 + heuristic rerank + evidence window
- Grounded answer + verifiable citation
- Source catalog / source drawer / source scope
- Watchdog 增量同步
- Workflow trace 可观测性

**已验证可扩展的能力：**

- URL extraction
- Image OCR
- CSV source skill
- Source Skill Contract 作为多源/多模态接入规范

**后续工作应集中在：**

- 论文和答辩材料整理
- 不是继续扩展功能

---

## 附录：测试命令速查

```powershell
# 核心回归
conda run --no-capture-output -n minddock python -m pytest tests/unit/test_evidence_window.py tests/unit/test_retrieval_models.py tests/unit/test_pdf_citation.py tests/unit/test_citation.py tests/unit/test_schemas.py tests/unit/test_postprocess.py tests/unit/test_chat_service.py tests/unit/test_search_service.py tests/unit/test_csv_loader.py tests/unit/test_source_skill_catalog.py -q

# 全量回归
conda run --no-capture-output -n minddock python -m pytest tests/unit/ -q

# 前端构建
cd frontend
npm run build
```
