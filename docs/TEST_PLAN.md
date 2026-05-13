# Test Plan

## Objective

Keep MindDock's MVP behavior stable while the retrieval and orchestration layers evolve.

## Test Layers

### Unit

- Schema validation
- Service logic with mocked dependencies
- Splitter and utility behavior
- Incremental ingest create / modify / delete behavior
- Reranker/compressor behavior
- Mermaid structured output rendering
- Lightweight evaluation helper behavior
- Media transcript provider resolution and Local ASR boundary behavior
- Source Skill manifest validation and trusted handler behavior
- Schedule-candidate extraction and status transitions

### Integration

- HTTP routes with `TestClient`
- Request and response contract validation
- Minimal app startup path
- Watch handler event forwarding at small granularity
- Frontend unified execution, SSE projection, event replay, and cancellation
- Runtime and media transcript configuration endpoints

### Contract

- `domain` dataclass fields
- `ports` method signatures and extension boundaries

## Minimum Local Validation

Run before pushing significant changes:

```bash
python -m pytest
```

Run the local CI baseline when preparing a push or thesis-demo checkpoint:

```bash
python scripts/run_ci_baseline.py
```

If ingestion or retrieval code changed, also run:

```bash
python -m app.rag.ingest --rebuild
```

If post-retrieval logic or summarize modes changed, also run:

```bash
python -m pytest tests/unit/test_postprocess.py tests/unit/test_summarize_service.py tests/unit/test_structured_output_service.py
```

If frontend unified execution, streaming, or run control changed, also run:

```bash
python -m pytest tests/unit/test_application_orchestrators.py tests/unit/test_client_events.py tests/unit/test_run_control.py
```

If media transcript, Local ASR, or Source Skill behavior changed, also run the matching focused tests:

```bash
python -m pytest tests/unit/test_media_loader.py tests/unit/test_media_transcript_postprocessor.py tests/unit/test_source_skill_coverage_edges.py
```

If schedule extraction changed, run schedule-focused tests if present and manually exercise:

```bash
python -m pytest tests/unit/test_schedule_candidate_service.py tests/unit/test_schedule_extractor.py tests/unit/test_schedule_store.py tests/integration/test_schedule_candidate_api.py tests/integration/test_schedule_skill_api.py
curl http://127.0.0.1:8000/frontend/schedule-candidates
```

If experiment/evaluation helpers changed, also run:

```bash
python scripts/evaluate_rag.py
```

If incremental maintenance changed, also review:

```bash
python -m pytest tests/unit/test_incremental_ingest.py tests/unit/test_watcher.py
```

For defense demo preparation, also verify:

```bash
python -m app.rag.ingest --rebuild
```

Then manually exercise:

- `/search`
- `/chat`
- `/summarize`
- `/compare` (requires at least 2 indexed documents for meaningful output)
- `/frontend/execute` and `/frontend/execute/stream`
- `/frontend/runtime-config`
- `/frontend/media-transcript-config`
- `/frontend/source-skills`
- `/frontend/schedule-candidates`
- watcher-based incremental maintenance

Recommended demo dataset:

- `knowledge_base/example.md`
- `knowledge_base/architecture.md`
- `knowledge_base/api_usage.md`

## Deferred

- Performance benchmarks
- Larger citation quality evaluation dataset
- End-to-end workflow replay tests
