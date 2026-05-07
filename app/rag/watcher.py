"""Watch knowledge base files and trigger per-document incremental ingest."""

from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path

from app.core.config import get_settings
from app.core.logging import setup_logging
from app.rag.incremental import IncrementalIngestService

logger = logging.getLogger(__name__)


class _WatchHandler:
    """Bridge watchdog events to the incremental ingest service."""

    def __init__(self, service: IncrementalIngestService) -> None:
        from watchdog.events import FileSystemEventHandler

        class Handler(FileSystemEventHandler):
            def on_created(self, event) -> None:  # type: ignore[no-untyped-def]
                if event.is_directory:
                    return
                service.handle_created(Path(event.src_path))

            def on_modified(self, event) -> None:  # type: ignore[no-untyped-def]
                if event.is_directory:
                    return
                service.handle_modified(Path(event.src_path))

            def on_deleted(self, event) -> None:  # type: ignore[no-untyped-def]
                if event.is_directory:
                    return
                service.handle_deleted(Path(event.src_path))

            def on_moved(self, event) -> None:  # type: ignore[no-untyped-def]
                if event.is_directory:
                    return
                service.handle_deleted(Path(event.src_path))
                service.handle_created(Path(event.dest_path))

        self.instance = Handler()


def run_watcher(
    *,
    path: str | Path | None = None,
    debounce_seconds: float | None = None,
    once: bool = False,
    dry_run: bool = False,
    ready_file: str | Path | None = None,
    fail_on_sync_error: bool = False,
) -> list:
    """Start the watchdog observer and block forever."""

    try:
        from watchdog.observers import Observer
    except Exception as exc:
        raise RuntimeError(
            "watchdog is required for incremental watch mode. Install it with `pip install watchdog`."
        ) from exc

    settings = get_settings()
    setup_logging(settings.log_level, settings.log_dir, settings.app_name)
    if not settings.watch_enabled:
        raise RuntimeError("WATCH_ENABLED must be true before starting the watcher")

    watch_path = Path(path or settings.watch_path).resolve()
    watch_path.mkdir(parents=True, exist_ok=True)

    service = IncrementalIngestService(kb_dir=watch_path, debounce_seconds=debounce_seconds)
    sync_results = service.sync_directory(dry_run=dry_run)
    for result in sync_results:
        print(_format_result(result))
    failed_results = [result for result in sync_results if result.status == "failed"]
    ready_status = _ready_status_for_sync(sync_results)
    if failed_results and fail_on_sync_error:
        _write_ready_file(
            ready_file,
            status="failed",
            watch_path=watch_path,
            sync_results=sync_results,
            detail=f"{len(failed_results)} sync result(s) failed",
        )
        raise RuntimeError(f"Watcher sync failed for {len(failed_results)} source(s); see watcher log.")
    if once or dry_run:
        _write_ready_file(
            ready_file,
            status=ready_status,
            watch_path=watch_path,
            sync_results=sync_results,
            detail="sync completed",
        )
        return sync_results

    handler = _WatchHandler(service).instance
    observer = Observer()
    observer.schedule(handler, str(watch_path), recursive=settings.watch_recursive)
    observer.start()
    _write_ready_file(
        ready_file,
        status=ready_status,
        watch_path=watch_path,
        sync_results=sync_results,
        detail="observer started",
    )
    print(f"Watcher Ready: {watch_path}", flush=True)

    logger.info(
        "Knowledge base watcher started: watch_path=%s recursive=%s debounce_seconds=%s log_dir=%s",
        str(watch_path),
        settings.watch_recursive,
        settings.watch_debounce_seconds if debounce_seconds is None else debounce_seconds,
        settings.log_dir,
    )

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Knowledge base watcher stopping")
        observer.stop()
    observer.join()
    return sync_results


def main() -> None:
    parser = argparse.ArgumentParser(description="Watch knowledge base files and incrementally ingest changes")
    parser.add_argument("--once", action="store_true", help="Run one directory sync and exit")
    parser.add_argument("--dry-run", action="store_true", help="Preview sync changes without writing Chroma or HashStore")
    parser.add_argument("--path", default=None, help="Knowledge base directory to watch")
    parser.add_argument("--debounce", type=float, default=None, help="Debounce seconds for filesystem events")
    parser.add_argument("--ready-file", default=None, help="Write a JSON readiness marker after sync/observer startup")
    parser.add_argument("--fail-on-sync-error", action="store_true", help="Exit if the initial sync reports failed sources")
    args = parser.parse_args()
    run_watcher(
        path=args.path,
        debounce_seconds=args.debounce,
        once=args.once,
        dry_run=args.dry_run,
        ready_file=args.ready_file,
        fail_on_sync_error=args.fail_on_sync_error,
    )


def _format_result(result) -> str:
    parts = [
        f"{result.event_type}",
        result.status,
        result.descriptor.source,
    ]
    if result.chunks_upserted:
        parts.append(f"upserted={result.chunks_upserted}")
    if result.chunks_deleted:
        parts.append(f"deleted={result.chunks_deleted}")
    if result.detail:
        parts.append(result.detail)
    return " | ".join(parts)


def _write_ready_file(
    ready_file: str | Path | None,
    *,
    status: str,
    watch_path: Path,
    sync_results: list,
    detail: str,
) -> None:
    if ready_file is None:
        return
    path = Path(ready_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": status,
        "watch_path": str(watch_path),
        "detail": detail,
        "sync_total": len(sync_results),
        "sync_failed": sum(1 for result in sync_results if result.status == "failed"),
        "sync_degraded": sum(1 for result in sync_results if result.status == "degraded"),
        "sync_empty": sum(1 for result in sync_results if result.status == "empty"),
        "sync_updated": sum(1 for result in sync_results if result.status == "updated"),
        "sync_removed": sum(1 for result in sync_results if result.status in {"deleted", "removed"}),
        "sync_skipped": sum(1 for result in sync_results if result.status == "skipped"),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _ready_status_for_sync(sync_results: list) -> str:
    if any(result.status == "failed" for result in sync_results):
        return "failed"
    if any(result.status == "degraded" for result in sync_results):
        return "degraded"
    if any(result.status == "empty" for result in sync_results):
        return "empty"
    return "ready"


if __name__ == "__main__":
    main()
