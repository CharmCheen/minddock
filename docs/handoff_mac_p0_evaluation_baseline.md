# Handoff: mac-p0-evaluation-baseline

> Generated: 2026-05-28 | Branch: `mac-p0-evaluation-baseline` | Based on: `master`

---

## 1. Branch

- **Current branch:** `mac-p0-evaluation-baseline`
- **Created from:** `master` (commit `7834239`)
- **Purpose:** P0 evaluation baseline — first phase only

## 2. Goal

本分支目标是 **P0 evaluation baseline 的第一阶段**：

- 扩展 evaluation 数据模型，支持 insufficient evidence 检测评测
- 在 metrics/runner/reporting 中接入 insufficient evidence 指标
- 创建扩展 golden eval 数据集
- 补充评测相关单元测试

**不是** 以下内容：
- 不是 hybrid retrieval 优化
- 不是 cross-encoder reranker 接入
- 不是 NLI citation verification
- 不是 RAG 质量 benchmark 跑分

## 3. Files Changed

### Modified (8 files)

| File | Change |
|------|--------|
| `app/evaluation/__init__.py` | 导出 `InsufficientEvidenceEvaluation` |
| `app/evaluation/models.py` | `BenchmarkCase` 添加 `expected_insufficient_evidence`；新增 `InsufficientEvidenceEvaluation`；`EvaluationCaseResult` 添加 `insufficient_evidence_eval`；`EvaluationSummary` 添加 `insufficient_evidence` |
| `app/evaluation/metrics.py` | 新增 `evaluate_insufficient_evidence()`；`summarize_results()` 添加 IE 聚合指标 |
| `app/evaluation/runner.py` | 集成 `evaluate_insufficient_evidence`；`_build_failure_reasons` 增加 `insufficient_evidence_mismatch` |
| `app/evaluation/reporting.py` | Console/Markdown 报告添加 Insufficient Evidence Detection 段落和 IE Correct 列 |
| `eval/benchmark/sample_eval_set.jsonl` | 为 `chat_insufficient_token_rotation` 添加 `expected_insufficient_evidence: true` |
| `tests/unit/test_evaluation.py` | 新增 5 个 IE 测试；更新 fake summary 包含 `insufficient_evidence` |
| `tests/unit/test_rag_eval.py` | 更新 fake summary 包含 `insufficient_evidence` |

### New (1 file)

| File | Purpose |
|------|---------|
| `eval/benchmark/golden_eval_set.jsonl` | 19 cases: 8 search, 8 chat, 3 compare；4 个 IE case |

### Untracked (not part of this branch's scope)

| File | Purpose |
|------|---------|
| `docs/zoom_out_project_audit.md` | 全局技术审计报告（审计产物，非功能代码） |
| `docs/defense_source_guide.md` | 答辩准备文档 |
| `docs/defense_source_guide_v2.md` | 答辩准备文档 v2 |

## 4. What Was Implemented

### 4.1 Insufficient Evidence Evaluation Model

`BenchmarkCase` 新增 `expected_insufficient_evidence: bool` 字段，默认 `False`。

`InsufficientEvidenceEvaluation` 是一个 frozen dataclass：
```python
@dataclass(frozen=True)
class InsufficientEvidenceEvaluation:
    expected: bool   # benchmark case 期望的拒答标记
    actual: bool     # 系统实际返回的 insufficient_evidence
    correct: bool    # expected == actual
```

- Evidence: `app/evaluation/models.py:121-133`

### 4.2 Metric Calculation

`evaluate_insufficient_evidence(case, response)` 函数：
- 读取 `case.expected_insufficient_evidence`
- 读取 `response.metadata.insufficient_evidence`
- 返回 `InsufficientEvidenceEvaluation(expected, actual, correct)`

- Evidence: `app/evaluation/metrics.py:143-155`

### 4.3 Aggregated Metrics

`summarize_results()` 新增 `insufficient_evidence` 字段：
- `accuracy`: 所有 case 中 IE 判断正确的比例
- `refusal_precision`: 期望拒答的 case 中实际拒答的比例
- `non_refusal_accuracy`: 期望不拒答的 case 中实际不拒答的比例
- `expected_refusal_count`: 期望拒答的 case 数
- `actual_refusal_count`: 实际拒答的 case 数

- Evidence: `app/evaluation/metrics.py:254-267`

### 4.4 Runner Integration

`run_case()` 调用 `evaluate_insufficient_evidence(case, response)`，结果传入 `EvaluationCaseResult.insufficient_evidence_eval`。

`_build_failure_reasons()` 新增 `insufficient_evidence_mismatch` 失败原因。

- Evidence: `app/evaluation/runner.py:69-70, 110-119`

### 4.5 Reporting

- Console summary 新增 `Insufficient Evidence:` 行
- Markdown report 新增 `## Insufficient Evidence Detection` 段落（表格形式）
- Case Details 表新增 `IE Correct` 列

- Evidence: `app/evaluation/reporting.py:14-37, 81-89, 121-135`

### 4.6 Golden Set Organization

`eval/benchmark/golden_eval_set.jsonl` 包含 19 个 case：

| Task Type | Count | IE Cases |
|-----------|-------|----------|
| search | 8 | 0 |
| chat | 8 | 4 |
| compare | 3 | 0 |

IE cases 设计为系统知识库中不存在答案的问题（token rotation、horizontal scaling、ML training、database migration）。

- Evidence: `eval/benchmark/golden_eval_set.jsonl`

### 4.7 Test Coverage

新增 5 个测试：

| Test | Covers |
|------|--------|
| `test_evaluate_insufficient_evidence_correct_refusal` | 正确拒答 |
| `test_evaluate_insufficient_evidence_missed_refusal` | 漏拒答 |
| `test_evaluate_insufficient_evidence_false_refusal` | 误拒答 |
| `test_evaluate_insufficient_evidence_correct_answer` | 正确不拒答 |
| `test_run_evaluation_from_dataset_with_insufficient_evidence_case` | 端到端 IE 评测 |

- Evidence: `tests/unit/test_evaluation.py` (IE test section)

## 5. What Was Not Implemented

- **没有接 cross-encoder reranker** — `app/rag/postprocess.py` 仍使用 heuristic reranker
- **没有开启 hybrid retrieval** — `hybrid_retrieval_enabled` 仍默认 `False`
- **没有实现 NLI citation verification** — citation 仍基于 retrieved chunk 直接映射
- **没有运行真实 RAG 评测** — 未执行 `scripts/evaluate_rag.py`
- **没有验证指标是否在完整环境下能跑通** — 未运行 pytest
- **没有创建 deterministic evaluation fixtures** — golden set 依赖用户知识库中的特定文档

## 6. Validation Status

**当前 Mac 环境未安装完整 MindDock 依赖，因此未实际运行：**

- `pytest tests/unit/test_evaluation.py`
- `pytest tests/unit/test_rag_eval.py`
- `python scripts/evaluate_rag.py`
- `python -m app.main` (backend)
- `npm run dev` (frontend)
- ChromaDB / vector store
- ASR / LLM runtime

**已完成的静态验证：**

- 所有修改的 Python 文件通过 `ast.parse()` 语法检查
- `golden_eval_set.jsonl` 通过 JSON 解析和 schema 验证（19 cases, 4 IE cases）
- `sample_eval_set.jsonl` 通过 JSON 解析验证（13 cases, 1 IE case）
- Import 路径一致性检查通过

## 7. Commands To Run In Full Environment

```bash
# 安装依赖
pip install -e ".[dev]"

# 运行评测相关单元测试
pytest tests/unit/test_evaluation.py tests/unit/test_rag_eval.py -v

# 运行全量测试
pytest tests/ -v

# 运行 sample eval dataset
python scripts/evaluate_rag.py \
  --dataset eval/benchmark/sample_eval_set.jsonl \
  --output-dir data/eval

# 运行 golden eval dataset
python scripts/evaluate_rag.py \
  --dataset eval/benchmark/golden_eval_set.jsonl \
  --output-dir data/eval

# 查看报告
cat data/eval/golden_eval_set_evaluation_report.md
```

## 8. Risk Notes

### 8.1 `expected_insufficient_evidence` 与 `expected_support_status`

**当前无冲突。** `BenchmarkCase` 中不存在 `expected_support_status` 字段。`expected_insufficient_evidence` 是唯一的证据期望字段。

**潜在问题：** 系统实际有三种 `SupportStatus`（`SUPPORTED`, `PARTIALLY_SUPPORTED`, `INSUFFICIENT_EVIDENCE`），但评测只检查 boolean。如果未来需要区分 `PARTIALLY_SUPPORTED`，需要扩展为 `expected_support_status: str`。

**建议：** P0 阶段 boolean 够用。P1 阶段可扩展为 enum。

### 8.2 Golden Set Fixture 依赖

**当前有依赖风险。** `golden_eval_set.jsonl` 的 15 个非 IE case 引用固定的 `expected_doc_ids`（如 `56b97ed9cc7de1ecc311f1ecfd9454276e83842d`），这些是基于特定文档路径计算的 SHA-1 哈希。如果知识库中不存在对应的 `example.md`、`architecture.md`、`rag_pipeline.md`、`api_usage.md`，retrieval 指标将全部失败。

**建议：** 下一步应创建 `eval/benchmark/fixtures/` 目录，包含最小可复现的 fixture 文档。

### 8.3 三类指标完整性

| 指标类别 | 函数 | 状态 |
|----------|------|------|
| Retrieval | `evaluate_retrieval()` → `hit_at_1/3/5` | 已存在（本轮未修改） |
| Citation | `evaluate_citation_consistency()` → `structure_consistent`, `expected_source_consistent` | 已存在（本轮未修改） |
| Insufficient Evidence | `evaluate_insufficient_evidence()` → `correct` | 本轮新增 |
| Latency | `summarize_latencies()` → `avg/p50/p95/max` | 已存在（本轮未修改） |

**结论：** 三类核心指标 + latency 均已覆盖。

### 8.4 `EvaluationSummary` 新增字段的兼容性

`EvaluationSummary` 新增了 `insufficient_evidence: dict[str, float | int]` 字段。

**影响：**
- 所有手动构造 `EvaluationSummary` 的测试代码需要更新（已更新 `test_evaluation.py` 和 `test_rag_eval.py`）
- 旧的 JSON 报告文件如果被 `EvaluationSummary.from_dict()` 反序列化，会因缺少字段而失败（但当前没有 `from_dict` 方法，只有 `to_dict`）
- `asdict()` 序列化会自动包含新字段

**结论：** 无兼容性风险。旧报告文件不需要迁移。

### 8.5 Fake Summary 的测试价值

`test_rag_eval.py` 的 fake summary 仅为适配新字段结构，未验证真实评测行为。这是合理的——该测试的目的是验证 `evaluate_cases()` 委托给新模块的路由正确性，而非评测指标准确性。真实行为由 `test_evaluation.py::test_run_evaluation_from_dataset_happy_path` 覆盖。

## 9. Recommended Next Step

**不要进入 hybrid retrieval 或 reranker。**

下一步应优先做：

1. **创建 deterministic evaluation fixtures**
   - 在 `eval/benchmark/fixtures/` 下放入 `example.md`、`architecture.md`、`rag_pipeline.md`、`api_usage.md`
   - 这些文档的内容应与 golden set 中的 `expected_doc_ids` / `expected_chunk_ids` 对应
   - 确保 golden set 不依赖用户私有知识库

2. **在完整环境运行测试和评测**
   - `pytest tests/unit/test_evaluation.py tests/unit/test_rag_eval.py -v`
   - `python scripts/evaluate_rag.py --dataset eval/benchmark/golden_eval_set.jsonl --output-dir data/eval`

3. **生成第一份 baseline report**
   - 记录 retrieval hit@k、citation consistency、IE accuracy 的 baseline 数值
   - 作为后续改进的对照基准

## 10. Suggested Next Prompt

```
在 mac-p0-evaluation-baseline 分支上，补齐 deterministic evaluation fixtures，确保 golden eval set 不依赖用户私有知识库。

具体任务：
1. 创建 eval/benchmark/fixtures/ 目录
2. 在其中放入 example.md、architecture.md、rag_pipeline.md、api_usage.md 四个最小文档
3. 文档内容应覆盖 golden_eval_set.jsonl 中引用的所有 expected_doc_ids 和 expected_chunk_ids
4. 更新 scripts/evaluate_rag.py 或新增一个脚本，支持 --fixture-dir 参数，自动将 fixtures 目录作为知识库
5. 在完整环境运行 pytest 和评测脚本，验证所有 case 能跑通
6. 生成第一份 baseline report 并记录指标数值

限制：
- 不要修改 evaluation 主逻辑
- 不要添加新的指标
- 不要开启 hybrid retrieval 或 reranker
- 本轮目标是让 eval pipeline 在任何环境下可复现
```

---

## Static Self-Check

### 1. `expected_insufficient_evidence` 是否可以由 `expected_support_status` 推导？

**不存在 `expected_support_status` 字段。** `BenchmarkCase` 中只有 `expected_insufficient_evidence: bool`。系统实际有 `SupportStatus` enum（`SUPPORTED`, `PARTIALLY_SUPPORTED`, `INSUFFICIENT_EVIDENCE`），但评测模型只检查 boolean。

**当前无重复风险。** 如果未来添加 `expected_support_status`，则 `expected_insufficient_evidence` 可由 `expected_support_status == "insufficient_evidence"` 推导，届时可考虑移除 boolean 字段。

### 2. `golden_eval_set.jsonl` 是否依赖固定 fixture？

**是，有依赖风险。** 15 个非 IE case 引用固定的 `expected_doc_ids`（SHA-1 哈希），这些哈希基于特定文件路径计算。如果知识库中不存在对应文档，retrieval 指标将全部失败。

4 个 IE case 不依赖 fixture（`expected_doc_ids` 为空），它们测试的是系统对无答案问题的拒答能力。

**建议：** 创建 `eval/benchmark/fixtures/` 包含最小可复现文档。

### 3. 三类指标覆盖情况

| 指标 | 函数 | 文件 |
|------|------|------|
| **Retrieval** | `evaluate_retrieval()` → `hit_at_1/3/5` | `app/evaluation/metrics.py:118-140` |
| **Citation** | `evaluate_citation_consistency()` → `structure_consistent`, `expected_source_consistent` | `app/evaluation/metrics.py:158-204` |
| **Insufficient Evidence** | `evaluate_insufficient_evidence()` → `correct` | `app/evaluation/metrics.py:143-155` |
| **Latency** | `summarize_latencies()` → `avg/p50/p95/max` | `app/evaluation/metrics.py:207-220` |

三类核心指标均已覆盖。

### 4. 最可能的运行失败点

1. **`get_frontend_facade()` 初始化** — 需要 ChromaDB、embedding model、LLM runtime
2. **`get_settings()` 配置** — 需要 `.env` 或环境变量
3. **Chroma collection 访问** — 需要已创建的 `knowledge_base` collection
4. **Embedding model 加载** — 需要 `Qwen/Qwen3-Embedding-0.6B` 模型文件
5. **`from app.application import ...`** — 触发整个应用层初始化链

**Unit tests 使用 `FakeFacade` 绕过了这些问题，但 `scripts/evaluate_rag.py` 需要真实环境。**

### 5. 是否需要 `eval/benchmark/fixtures/`？

**是，建议创建。** 理由：

- 当前 golden set 的 15 个非 IE case 依赖用户知识库中的特定文档
- 不同用户的知识库不同，eval 结果不可复现
- CI/CD 环境没有用户知识库

建议结构：
```
eval/benchmark/fixtures/
├── example.md
├── architecture.md
├── rag_pipeline.md
└── api_usage.md
```

这些文档应为最小版本，只包含 golden set 引用的 section 内容。不需要完整文档。

---

## Phase 2: Deterministic Fixtures (2026-05-28)

### What Was Added

| File | Purpose |
|------|---------|
| `eval/benchmark/fixtures/example.md` | Project overview fixture |
| `eval/benchmark/fixtures/architecture.md` | Architecture fixture |
| `eval/benchmark/fixtures/rag_pipeline.md` | RAG pipeline fixture |
| `eval/benchmark/fixtures/api_usage.md` | API usage fixture |
| `eval/benchmark/fixtures/README.md` | Fixture usage documentation |
| `tests/unit/test_evaluation_fixtures.py` | Static fixture/golden-set consistency tests |
| `docs/evaluation_baseline_plan_or_result.md` | Evaluation baseline documentation |

### Fixture ↔ Golden Set Alignment

All 4 fixture doc_ids match golden set `expected_doc_ids`:

| Fixture | Doc ID | Golden Set Cases |
|---------|--------|-----------------|
| `example.md` | `56b97ed9...` | 4 supported cases |
| `architecture.md` | `b82bfe7e...` | 3 supported cases |
| `rag_pipeline.md` | `97a1bf3b...` | 3 supported cases |
| `api_usage.md` | `5f791bd9...` | 5 supported cases |

4 IE cases correctly have no fixture dependency.

### Doc ID Stability

`doc_id = sha1(relative_path)`. Renaming fixtures breaks golden set alignment. This is documented in `eval/benchmark/fixtures/README.md`.

### Static Tests Added

`tests/unit/test_evaluation_fixtures.py` covers:
- Fixture directory exists
- All expected fixture files exist
- Fixture documents are non-empty
- Fixture documents have section headings
- Golden set doc_ids match fixture doc_ids
- Sample set doc_ids match fixture doc_ids
- Golden set is parseable
- Golden set covers all task types
- Golden set has IE cases
- Supported cases have expected_doc_ids
- IE cases have empty expected_doc_ids
- All cases have non-empty queries
- All cases have unique IDs
- Query keywords hit fixture content

### Validation Status

- **Static tests:** All Python files pass `ast.parse()`. All JSONL files pass JSON validation.
- **Runtime tests:** NOT run (Mac environment, no dependencies).
- **Ingest verification:** NOT done (no Chroma/embedding).

### Complete Environment Commands

```bash
# Static fixture tests
pytest tests/unit/test_evaluation_fixtures.py -v

# Unit tests (FakeFacade, no Chroma needed)
pytest tests/unit/test_evaluation.py tests/unit/test_rag_eval.py -v

# Ingest fixtures
KB_DIR=eval/benchmark/fixtures python -c "from app.rag.ingest import ingest; ingest(rebuild=True)"

# Run golden eval
python scripts/evaluate_rag.py --dataset eval/benchmark/golden_eval_set.jsonl --output-dir data/eval
```

### Should We Enter P1?

**No, not yet.** Before P1 (hybrid retrieval / reranker), we need:
1. Run `pytest tests/unit/test_evaluation_fixtures.py -v` — confirm all static tests pass
2. Ingest fixtures — confirm Chroma can load them
3. Run golden eval — generate first baseline report
4. Record baseline metrics — these become the comparison target for P1
