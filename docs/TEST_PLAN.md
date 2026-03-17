# Test Plan

## Objective

Keep MindDock's MVP behavior stable while the retrieval and orchestration layers evolve.

## Test Layers

### Unit

- Schema validation
- Service logic with mocked dependencies
- Splitter and utility behavior
- Incremental ingest create / modify / delete behavior

### Integration

- HTTP routes with `TestClient`
- Request and response contract validation
- Minimal app startup path
- Watch handler event forwarding at small granularity

### Contract

- `domain` dataclass fields
- `ports` method signatures and extension boundaries

## Minimum Local Validation

Run before pushing significant changes:

```bash
python -m pytest
```

If ingestion or retrieval code changed, also run:

```bash
python -m app.rag.ingest --rebuild
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
- watcher-based incremental maintenance

Recommended demo dataset:

- `knowledge_base/example.md`

## Deferred

- Performance benchmarks
- Citation quality evaluation dataset
- End-to-end workflow replay tests
