# MindDock Evaluation Baseline Validation Result

## 1. Environment

- Date: 2026-05-29
- Workspace: `D:\大学\毕业设计\code\V0.1`
- Shell: PowerShell
- Python environment: conda env `minddock`
- Python: `Python 3.11.15`
- pip: `pip 26.0.1 from D:\conda_envs\minddock\Lib\site-packages\pip`
- Dependency install: PASS with `D:\conda_envs\minddock\python.exe -m pip install -e ".[dev]"`

Note: an earlier attempt with repository `.venv` failed because that venv uses Python 3.13.9 while `environment.yml` declares Python 3.11. The successful validation result in this report uses the intended `conda minddock` environment.

## 2. Branch and Commit

- Branch requested: `mac-p0-evaluation-baseline`
- Current branch: `mac-p0-evaluation-baseline`
- Remote tracking branch: `origin/mac-p0-evaluation-baseline`
- Remote baseline commit validated: `bdfc509 Add deterministic RAG evaluation baseline fixtures`
- Local validation commit: pending at report update time
- Pull result: `Already up to date.`
- Working tree note: the tree contained multiple pre-existing modified and untracked files before validation. This report only covers P0 evaluation baseline files and the generated validation artifacts.

## 3. Commands Run

```powershell
git fetch origin
git switch mac-p0-evaluation-baseline
git pull --ff-only
git status --short --branch
git log --oneline -1
conda env list
conda run -n minddock python --version
conda run -n minddock python -m pip --version
D:\conda_envs\minddock\python.exe -m pip install -e ".[dev]"
D:\conda_envs\minddock\python.exe -m pytest tests/unit/test_evaluation_fixtures.py -v
D:\conda_envs\minddock\python.exe -m pytest tests/unit/test_evaluation.py tests/unit/test_rag_eval.py -v
```

Ingest/eval commands:

```powershell
$env:KB_DIR='eval/benchmark/fixtures'
$env:CHROMA_DIR='data/eval/chroma'
D:\conda_envs\minddock\python.exe -c "from app.rag.ingest import ingest; ingest(rebuild=True)"

# Direct fixture directory also ingested README.md, so a clean 4-document temp KB was used:
$env:KB_DIR='data/eval/fixtures_kb'
$env:CHROMA_DIR='data/eval/chroma'
D:\conda_envs\minddock\python.exe -c "from app.rag.ingest import ingest; ingest(rebuild=True)"

$env:CHROMA_DIR='data/eval/chroma'
D:\conda_envs\minddock\python.exe scripts\evaluate_rag.py --dataset eval\benchmark\golden_eval_set.jsonl --output-dir data\eval
D:\conda_envs\minddock\python.exe scripts\evaluate_rag.py --dataset eval\benchmark\sample_eval_set.jsonl --output-dir data\eval
```

## 4. Unit Test Results

PASS after minimal fixture text alignment.

- `tests/unit/test_evaluation_fixtures.py -v`: 16 passed, 0 failed
- `tests/unit/test_evaluation.py tests/unit/test_rag_eval.py -v`: 20 passed, 0 failed
- Total evaluation-related unit tests run: 36 passed, 0 failed

Initial fixture test failures:

- `tests/unit/test_evaluation_fixtures.py::test_golden_queries_have_keyword_hits_in_fixtures`
- Cause 1: `search_source_lifecycle` query keywords had fewer than 2 hits in `eval/benchmark/fixtures/api_usage.md`.
- Cause 2: `chat_citation_fields` query keywords had fewer than 2 hits in `eval/benchmark/fixtures/example.md`.
- Cause 3: `compare_example_vs_api` query keywords had fewer than 2 hits in `eval/benchmark/fixtures/example.md`.

Minimal fix applied:

- Updated `eval/benchmark/fixtures/api_usage.md` Source Management wording to include "operations ... managing indexed sources".
- Updated `eval/benchmark/fixtures/example.md` Citations/Overview wording to include chat, summarize, search, and interface terms already implied by the fixture.

## 5. Fixture Ingest Results

PASS.

Direct command against `eval/benchmark/fixtures`:

- Loaded documents: 5
- Created chunks: 38
- Result: technically successful, but it included `README.md`, while the P0 target is 4 deterministic fixture documents.

Clean 4-document ingest used for baseline:

- KB directory: `data/eval/fixtures_kb`
- Chroma directory: `data/eval/chroma`
- Documents copied from fixtures: `example.md`, `architecture.md`, `rag_pipeline.md`, `api_usage.md`
- Loaded documents: 4
- Created chunks: 26
- Store isolation: independent eval Chroma store under `data/eval/chroma`
- Private KB risk: no `knowledge_base/` ingest was run

Runtime warnings observed:

- Chroma telemetry warnings: `capture() takes 1 positional argument but 3 were given`
- PyTorch warning: `torch_dtype` deprecation and Windows CUDA allocator warning
- These warnings did not fail ingest.

## 6. Golden Eval Results

PASS: golden eval command completed and generated reports.

- Dataset: `eval/benchmark/golden_eval_set.jsonl`
- Output JSON: `data/eval/golden_eval_set_evaluation_report.json`
- Output Markdown: `data/eval/golden_eval_set_evaluation_report.md`
- Total cases: 19
- Passed cases: 6
- Failed cases: 13

Sample eval was also run successfully:

- Dataset: `eval/benchmark/sample_eval_set.jsonl`
- Total cases: 13
- Passed cases: 4
- Failed cases: 9

## 7. Baseline Metrics

Golden eval metrics:

- total cases: 19
- passed cases: 6
- failed cases: 13
- Recall@1 / hit@1: 21.05%
- Recall@3 / hit@3: 42.11%
- Recall@5 / hit@5: 42.11%
- source hit rate: 42.11% at top 5, represented by retrieval hit@5 in the current report
- chunk hit rate: metric unavailable because the current report does not publish a separate aggregate chunk hit rate; retrieval matching records `match_basis: chunk` per case
- citation_present_rate: metric unavailable because the current report does not publish a citation-present aggregate
- citation_source_accuracy: 55.56%, represented by expected-source consistency rate
- citation_chunk_accuracy: metric unavailable because the current report does not publish citation chunk accuracy
- unsupported_citation_count: metric unavailable because the current report publishes dangling citation keys per case, not an aggregate unsupported citation count
- insufficient evidence accuracy: 68.42%
- refusal_precision: 0.00%
- non_refusal_accuracy: 86.67%
- average_latency_ms: 100.03

Additional reported metrics:

- citation overall consistency rate: 78.95%
- citation structure consistency rate: 100.00%
- expected-source case count: 9
- insufficient evidence refusal recall: 0.00%
- expected refusal count: 4
- actual refusal count: 2
- latency p50: 95.19 ms
- latency p95: 188.65 ms
- latency max: 534.03 ms

## 8. Failed Cases

- `search_extension_points` (search): retrieval_miss@5
- `search_ingest_endpoint` (search): retrieval_miss@5
- `search_source_lifecycle` (search): retrieval_miss@5
- `search_example_citations` (search): retrieval_miss@5
- `chat_citation_fields` (chat): retrieval_miss@5
- `chat_architecture_flow` (chat): retrieval_miss@5, citation_expected_source_miss, insufficient_evidence_mismatch
- `chat_evidence_policy` (chat): retrieval_miss@5, citation_expected_source_miss, insufficient_evidence_mismatch
- `chat_insufficient_token_rotation` (chat): retrieval_miss@5, insufficient_evidence_mismatch
- `chat_insufficient_scaling` (chat): retrieval_miss@5, insufficient_evidence_mismatch
- `chat_insufficient_ml_training` (chat): retrieval_miss@5, insufficient_evidence_mismatch
- `chat_insufficient_database_migration` (chat): retrieval_miss@5, insufficient_evidence_mismatch
- `compare_architecture_vs_rag` (compare): citation_expected_source_miss
- `compare_example_vs_api` (compare): citation_expected_source_miss

## 9. Fixes Applied

- Minimal fixture wording alignment in `eval/benchmark/fixtures/api_usage.md`.
- Minimal fixture wording alignment in `eval/benchmark/fixtures/example.md`.
- Updated this validation report with real `conda minddock` results.

No changes were made to:

- main RAG behavior
- hybrid retrieval
- cross-encoder reranking
- NLI citation verification
- frontend UI
- agent/plugin extension

## 10. Remaining Risks

- Directly using `KB_DIR=eval/benchmark/fixtures` ingests `README.md` as a fifth document. The clean validation used a temporary four-document KB to preserve the intended fixture set.
- Golden eval completed, but the baseline quality is intentionally low: 13 of 19 cases failed under current static baseline behavior.
- Several aggregate metrics requested by the validation prompt are not yet emitted by the current report schema.
- Compare evaluation fell back from the LLM JSON path to heuristic compare due to JSON decode failures; the fallback completed and produced report metrics.
- The worktree still contains pre-existing unrelated modifications and untracked files outside this validation task.

## 11. Can We Enter P1?

Yes, from a P0 validation-gate perspective.

The required P0 validation steps now run in the intended `conda minddock` environment: dependencies install, evaluation unit tests pass, deterministic fixtures ingest into an isolated eval Chroma store, and the golden eval baseline report is generated. The baseline metrics include failed cases, but those are recorded baseline outcomes rather than execution blockers.
