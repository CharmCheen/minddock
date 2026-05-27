# MindDock 毕设答辩演示链路检查报告

检查日期：2026-05-27

## 总体结论

本次围绕答辩默认演示路径完成了后端契约、前端渲染、SSE、Sources、Runtime、Source Skill 与启动链路的综合修复和回归验证。核心风险已经收口：当最终 `support_status=insufficient_evidence` 时，公开 `citations/evidence` 清空，前端主结果区不展示 Sources/Citations；workflow trace 仍保留检索和执行过程，但不把候选片段命名为回答来源。

## 修复的问题

- 统一 Chat / Summarize / Compare / unified execute / SSE 的 `insufficient_evidence` 契约：顶层 citations、artifact citations、公开 evidence 均为空。
- 拒答文案改为 fail-soft 提示，说明当前知识库证据不足，并提示上传或放入相关 PDF、讲义、笔记、Markdown、TXT 后再生成摘要/对比/问答。
- 修复 `Document(page_content=None)` 类风险：检索、向量库读取、ingest、media derived chunks 均过滤 None/空文本，不把 `"None"` 展示给用户。
- Compare 支持稳定 `selected_source_ids/doc_id` 范围过滤，citations/evidence/artifact 不允许混入未选中 source；修复 Chroma 单 where 限制导致的 Compare 500。
- Compare 中文 query 时，LLM prompt 与 heuristic fallback 均要求解释性字段中文；空 JSON/空对比点不会渲染空 Comparison Result 卡片。
- Summarize 在选中 source 后走 `source_scoped_full_summary`，直接读取选中文档 chunks，并按文档顺序 map-reduce，不再只依赖 query-driven top_k。
- 前端 execute payload 发送 `selected_source_ids` 与 `filters.doc_id`；失败态屏蔽 Pydantic/LangChain/stack trace/raw validation error。

## 启动检查

- `start.bat` 已检查：默认启动 Local ASR、backend、watcher、frontend；backend 使用 conda `minddock`。
- 当前 health 检查结果：
  - backend `http://127.0.0.1:8000/health`：OK。
  - local ASR `http://127.0.0.1:9001/health`：OK。
  - frontend `http://127.0.0.1:3000/`：OK。
- `logs/startup.log` 最近记录显示 local-asr、backend、model ready；watcher 为 started/not verified。演示前建议确认 watcher 窗口仍在运行。

## 场景结果

- Sources 页面：`/sources` 返回 41 个 source，均为 ready；ready、source_type、chunk_count、更新时间、source_state 可用。当前存在若干重复/相似论文文件名，但均 ready，不建议现场删除数据。
- Chat 范围内：`MindDock Prompt Profile role` 实测 `supported`，顶层 citations=4，artifact citations=4。
- Chat 范围外：`introduce university physics` 实测 `insufficient_evidence`，顶层 citations=0，artifact citations=0，回答为友好拒答。
- Summarize：选中 `MindDock_演示测试文档.md` 实测 `supported`，`summary_mode=source_scoped_full_summary`，chunks_used=80，citations=4。
- Compare：推荐使用 `demo_docs/demo_agentic_assistant.md` 与 `demo_docs/demo_rag_design.md`，问题 `Compare workflow trace and citation grounding design in these documents` 实测 `supported`，citations=2，citation doc_id 只来自选中两篇。
- Compare 证据不足：选中不相关 source 或泛化问题时返回 `insufficient_evidence`，citations=0，不返回空模板。
- SSE：`/frontend/execute/stream` 范围外 Chat 实测事件包含 `run_started/progress/artifact/warning/completed`，artifact citations=0，support_status=`insufficient_evidence`。

## 推荐演示路径

1. 打开 Sources 页面，展示 `MindDock_演示测试文档.md` ready、80 chunks、source_type、更新时间，并展开 chunk preview/metadata。
2. Chat 范围内：问 `MindDock 的 Prompt Profile 有什么作用？`，预期 supported、中文回答、citations 正常。
3. 展开 workflow trace，说明 retrieval、rerank、compress、Prompt Profile、artifact 输出。
4. Chat 范围外：问 `介绍大学物理`，预期 insufficient_evidence、友好提示、无 Sources/Citations。
5. Summarize：选择 `MindDock_演示测试文档.md`，问 `总结这个文章`，预期 source_scoped_full_summary、中文摘要、citations 只来自该文档。
6. Compare：选择 `demo_docs/demo_agentic_assistant.md` 和 `demo_docs/demo_rag_design.md`，问 `Compare workflow trace and citation grounding design in these documents`，预期 supported、至少一条 difference/common、citations 只来自选中两篇。
7. Runtime 设置页：展示 provider、base_url、model、api_key configured/masked，不泄露真实 key。
8. Source Skill 设置页：说明这是受信任来源处理控制面，展示 extensions、capabilities、limitations、trusted、enabled，不表述为插件市场。

## 测试命令与结果

- `D:\conda_envs\minddock\python.exe -m pytest tests\unit\test_schemas.py tests\unit\test_chat_service.py tests\unit\test_summarize_service.py tests\unit\test_compare_service.py tests\unit\test_text_normalization.py -q`：154 passed，1 个 PyTorch allocator warning。
- `npm run build`：通过。
- `npm run test:smoke`：13 passed。
- `npx playwright test tests/source-list.spec.ts tests/runtime-settings.spec.ts tests/source-skills-settings.spec.ts --reporter=line`：25 passed。
- 临时后端 `8011` 实测：Chat in/out、Summarize source-scoped、Compare selected scope、SSE insufficient 均通过；测试后已停止临时进程。

## 人工注意事项

- 演示前不要重建向量库或删除知识库数据；当前 source 状态适合展示。
- 如果要展示中文 Compare，可先用推荐英文 compare 问题稳定出 supported，再说明中文 query 已在单测覆盖中文 fallback；中文泛化问题在部分 source pair 上可能诚实返回 insufficient。
- 普通快速 SSE 任务通常不会自然触发 heartbeat；heartbeat 属于长任务保活机制，已通过 execute-stream 回归测试覆盖。
- `startup.log` 在某些 Windows 控制台中可能显示中文路径 mojibake，不影响页面和 JSON 响应。

---

## Compare 空结果修复（2026-05-27）

### 问题描述

Compare 模式在以下场景返回 `COMPLETED` 但无实际对比内容：
- 前端选择 2 个 sources 后提问"这两个文章的区别是什么"
- 页面显示 `task=Comparison`, `status=COMPLETED`
- "Why this answer?" 显示 `Evidence: 0 citations from 2 sources`, `Warning: No citations were available for this answer`
- 主结果区无具体 common/differences/conflicts 内容
- comparison result 为空

### 根因定位

1. **后端 metadata 不一致**：当 LLM 返回空 JSON 且 heuristic fallback 也失败时，`_build_compare_result` 设置 `support_status=INSUFFICIENT_EVIDENCE`，但 compare 服务的正常完成路径没有将 `metadata.insufficient_evidence` 同步为 `True`。虽然 `UseCaseMetadata` 构造时有 `insufficient_evidence=compare_result.support_status == SupportStatus.INSUFFICIENT_EVIDENCE`，但在某些边界条件下（如 heuristic 产出空点后直接返回），citations 收集和 trace 构造在 insufficient 判定之前执行，导致前端收到 mixed 信号。

2. **前端 "Why this answer?" 误导**：`formatEvidenceSummary` 在 `final_citation_count=0` 时仍显示 "Evidence: 0 citations from 2 sources"，对用户无意义且造成困惑。

3. **前端 structured_json 渲染器**：`raw-artifact-viewer.tsx` 在 `!hasCompareContent` 时检查 `insufficientEvidence`，但未检查 `data.support_status`，导致在某些 metadata 传递路径下 insufficient 状态未被正确识别。

### 修复方式

1. **后端 compare_service.py**：在 `_compare_groups` 返回空点后，检测 `compare_result.support_status == INSUFFICIENT_EVIDENCE`，直接路由到 `_insufficient_result`，确保 `metadata.insufficient_evidence=True`、`citations=[]`、workflow trace 一致。

2. **前端 agent-message-list.tsx**：`formatEvidenceSummary` 在 `citationCount === 0` 时返回 `null`，不再显示 "0 citations from N sources"。

3. **前端 raw-artifact-viewer.tsx**：structured_json compare 渲染器在 `!hasCompareContent` 时额外检查 `dataObj.support_status === 'insufficient_evidence'`，确保 insufficient 状态下不显示空 Comparison Result 卡片。

### 修改文件

- `app/services/compare_service.py`：compare 方法增加 insufficient_evidence 后处理路由
- `frontend/src/features/agent/components/agent-message-list.tsx`：formatEvidenceSummary 跳过 0 citations
- `frontend/src/features/agent/components/raw-artifact-viewer.tsx`：structured_json compare 渲染器增加 support_status 检查
- `tests/unit/test_compare_service.py`：新增 9 个测试覆盖空结果、单侧无 chunks、citations 一致性、中文输出等场景

### 测试结果

- `test_compare_service.py`：68 passed（原有 59 + 新增 9）
- `test_schemas.py`：40 passed
- 全量 unit tests：579 passed, 1 failed（pre-existing `test_rag_coverage_edges` 失败，非本次修改引入）

### 推荐用于答辩演示的固定 Compare source pair

- Source A: `demo_docs/demo_agentic_assistant.md`
- Source B: `demo_docs/demo_rag_design.md`

### 推荐问题

- 英文: `Compare workflow trace and citation grounding design in these documents`
- 中文: `这两个文章的区别是什么`

### 预期结果摘要

- 英文 query: `supported`, differences ≥ 1, citations ≥ 2, citations 只来自选中两篇
- 中文 query: `supported`, differences ≥ 1, 中文 explanation, citations 只来自选中两篇
- 选中不相关 source: `insufficient_evidence`, citations=0, 前端显示友好提示, 不显示空 Comparison Result
- 一侧 source 无 chunks: `insufficient_evidence`, citations=0, 前端显示友好提示
