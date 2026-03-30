# Incremental Maintenance Demo

## Purpose

This demo shows the difference between:

- full rebuild via `python -m app.demo ingest`
- per-file incremental maintenance via `python -m app.demo watch`

## Recommended Demo Flow

1. Rebuild the knowledge base once:

```powershell
conda activate minddock
python -m app.demo ingest
```

2. Start the watcher in a separate terminal:

```powershell
conda activate minddock
python -m app.demo watch
```

3. Under `knowledge_base/`, perform these actions:

- create a new `.md` or `.txt` file
- modify `example.md` or another existing file
- delete a file

4. Explain the expected behavior:

- create: a new document is chunked and upserted
- modify: only the changed document is rebuilt
- delete: chunks for that document are removed from the vector store

## Notes

- The watcher is suitable for manual demo, but automated tests focus on the incremental service itself rather than OS-level observer timing.
- If the environment lacks `watchdog`, you can still demonstrate incremental correctness through the unit tests and the full ingest command.
