"""Watch knowledge base files and trigger per-document incremental ingest."""

from __future__ import annotations

import argparse
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

        self.instance = Handler()


def run_watcher() -> None:
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

    watch_path = Path(settings.watch_path).resolve()
    watch_path.mkdir(parents=True, exist_ok=True)

    service = IncrementalIngestService()
    handler = _WatchHandler(service).instance
    observer = Observer()
    observer.schedule(handler, str(watch_path), recursive=settings.watch_recursive)
    observer.start()

    logger.info(
        "Knowledge base watcher started: watch_path=%s recursive=%s debounce_seconds=%s log_dir=%s",
        str(watch_path),
        settings.watch_recursive,
        settings.watch_debounce_seconds,
        settings.log_dir,
    )

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Knowledge base watcher stopping")
        observer.stop()
    observer.join()


def main() -> None:
    parser = argparse.ArgumentParser(description="Watch knowledge base files and incrementally ingest changes")
    parser.parse_args()
    run_watcher()


if __name__ == "__main__":
    main()
