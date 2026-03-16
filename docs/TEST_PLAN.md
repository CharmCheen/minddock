# Test Plan

## Objective

Keep MindDock's MVP behavior stable while the retrieval and orchestration layers evolve.

## Test Layers

### Unit

- Schema validation
- Service logic with mocked dependencies
- Splitter and utility behavior

### Integration

- HTTP routes with `TestClient`
- Request and response contract validation
- Minimal app startup path

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

## Deferred

- Performance benchmarks
- Citation quality evaluation dataset
- End-to-end workflow replay tests
