"""Incremental document ingestion with debounce and hash checking."""

from __future__ import annotations

import hashlib
import json
import logging
import stat
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from app.core.config import get_settings
from app.rag.embeddings import EmbeddingBackend, get_embedding_backend
from app.rag.ingest import SUPPORTED_EXTENSIONS, build_payload_for_source
from app.rag.media_loader import MEDIA_EXTENSIONS, is_media_sidecar_transcript
from app.rag.source_loader import SourceLoaderRegistry, build_file_descriptor
from app.rag.source_models import IncrementalUpdateResult
from app.rag.vectorstore import count_document_chunks, get_vectorstore

logger = logging.getLogger(__name__)


class VectorCollection(Protocol):
    """Minimal collection protocol used by incremental ingest."""

    def replace_document(
        self,
        *,
        doc_id: str,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict[str, str]],
        embeddings: list[list[float]],
    ):
        """Replace one document's current chunks and remove stale ones."""


class HashStore:
    """Persist content hashes for watched documents."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._data = self._load()

    def _load(self) -> dict[str, dict[str, Any]]:
        if not self._path.exists():
            return {}
        try:
            loaded = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            logger.warning("Hash store is invalid, starting from empty store: %s", self._path)
            return {}
        if not isinstance(loaded, dict):
            return {}

        normalized: dict[str, dict[str, Any]] = {}
        for source_path, entry in loaded.items():
            if not isinstance(entry, dict):
                continue
            record: dict[str, Any] = {
                "doc_id": str(entry.get("doc_id") or ""),
                "content_hash": str(entry.get("content_hash") or ""),
                "status": str(entry.get("status") or "ready"),
                "error": entry.get("error"),
                "last_synced_at": entry.get("last_synced_at"),
            }
            for key in ("transcript_status", "transcript_provider", "transcript_error"):
                if key in entry:
                    record[key] = entry[key]
            normalized[str(source_path)] = record
        return normalized

    def save(self) -> None:
        self._path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get(self, source_path: str) -> dict[str, Any] | None:
        return self._data.get(source_path)

    def set(
        self,
        source_path: str,
        doc_id: str,
        content_hash: str,
        *,
        status: str = "ready",
        error: str | None = None,
        transcript_status: str = "",
        transcript_provider: str = "",
        transcript_error: str = "",
    ) -> None:
        entry: dict[str, Any] = {
            "doc_id": doc_id,
            "content_hash": content_hash,
            "status": status,
            "error": error,
            "last_synced_at": _utc_now_iso(),
        }
        if transcript_status:
            entry["transcript_status"] = transcript_status
            entry["transcript_provider"] = transcript_provider
            entry["transcript_error"] = transcript_error
        self._data[source_path] = entry
        self.save()

    def mark_failed(self, source_path: str, doc_id: str, error: str) -> None:
        previous = self._data.get(source_path, {})
        self._data[source_path] = {
            "doc_id": doc_id or str(previous.get("doc_id") or ""),
            "content_hash": str(previous.get("content_hash") or ""),
            "status": "failed",
            "error": error,
            "last_synced_at": _utc_now_iso(),
        }
        self.save()

    def remove(self, source_path: str) -> None:
        if source_path in self._data:
            del self._data[source_path]
            self.save()

    def items(self):
        return self._data.items()


class IncrementalIngestService:
    """Handle per-document incremental updates for the watched knowledge base."""

    def __init__(
        self,
        kb_dir: Path | None = None,
        debounce_seconds: float | None = None,
        hash_store: HashStore | None = None,
        loader_registry: SourceLoaderRegistry | None = None,
        embedder: EmbeddingBackend | None = None,
        collection: VectorCollection | None = None,
        count_document_chunks_fn=count_document_chunks,
    ) -> None:
        settings = get_settings()
        self._kb_dir = (kb_dir or Path(settings.watch_path)).resolve()
        self._debounce_seconds = (
            settings.watch_debounce_seconds if debounce_seconds is None else debounce_seconds
        )
        self._hash_store = hash_store or HashStore(Path(settings.hash_store_path))
        self._loader_registry = loader_registry or SourceLoaderRegistry()
        self._embedder = embedder or get_embedding_backend(settings.embedding_model)
        self._collection = collection or get_vectorstore()
        self._count_document_chunks = count_document_chunks_fn
        self._last_seen: dict[str, float] = {}

    def sync_directory(self, dry_run: bool = False) -> list[IncrementalUpdateResult]:
        """Synchronize the watched directory with indexed state known by HashStore."""

        self._kb_dir.mkdir(parents=True, exist_ok=True)
        results: list[IncrementalUpdateResult] = []
        current_sources: dict[str, Path] = {}

        for path in sorted(self._kb_dir.rglob("*")):
            if path.is_file() and self._is_supported(path):
                descriptor = self._build_descriptor(path)
                current_sources[descriptor.source] = path

        for source, path in current_sources.items():
            descriptor = self._build_descriptor(path)
            readable_error = self._readability_error(path)
            if readable_error is not None:
                if not dry_run:
                    self._hash_store.mark_failed(descriptor.source, descriptor.doc_id, readable_error)
                results.append(
                    IncrementalUpdateResult(
                        descriptor=descriptor,
                        event_type="sync",
                        status="failed",
                        detail=readable_error,
                    )
                )
                continue

            try:
                content_hash = self._compute_hash(path)
            except (OSError, PermissionError, FileNotFoundError) as exc:
                detail = f"file is not readable: {exc}"
                if not dry_run:
                    self._hash_store.mark_failed(descriptor.source, descriptor.doc_id, detail)
                results.append(
                    IncrementalUpdateResult(
                        descriptor=descriptor,
                        event_type="sync",
                        status="failed",
                        detail=detail,
                    )
                )
                continue

            stored = self._hash_store.get(source)
            if stored and stored.get("content_hash") == content_hash and stored.get("status") == "ready":
                if not self._needs_media_transcript_retry(path, stored):
                    results.append(
                        IncrementalUpdateResult(
                            descriptor=descriptor,
                            event_type="sync",
                            status="skipped",
                            detail="content hash unchanged",
                        )
                    )
                    continue
                # Media file needs re-transcription; fall through to re-process

            event_type = "created" if stored is None else "modified"
            if dry_run:
                results.append(
                    IncrementalUpdateResult(
                        descriptor=descriptor,
                        event_type=event_type,
                        status="planned",
                        detail=f"dry-run: would {'ingest' if stored is None else 'reindex'}",
                    )
                )
            else:
                results.append(self._handle_upsert(path=path, event_type=event_type, bypass_debounce=True))

        missing_sources = sorted(source for source, _entry in self._hash_store.items() if source not in current_sources)
        for source in missing_sources:
            stored = self._hash_store.get(source) or {}
            descriptor = build_file_descriptor((self._kb_dir / source).resolve(), self._kb_dir)
            if dry_run:
                results.append(
                    IncrementalUpdateResult(
                        descriptor=descriptor,
                        event_type="deleted",
                        status="planned",
                        detail="dry-run: would delete indexed chunks",
                    )
                )
                continue
            deleted = self._collection.replace_document(
                doc_id=str(stored.get("doc_id") or descriptor.doc_id),
                ids=[],
                documents=[],
                metadatas=[],
                embeddings=[],
            ).deleted
            self._hash_store.remove(source)
            results.append(
                IncrementalUpdateResult(
                    descriptor=descriptor,
                    event_type="deleted",
                    status="removed",
                    chunks_deleted=deleted,
                )
            )

        return results

    def handle_created(self, path: Path) -> IncrementalUpdateResult:
        return self._handle_upsert(path=path, event_type="created")

    def handle_modified(self, path: Path) -> IncrementalUpdateResult:
        return self._handle_upsert(path=path, event_type="modified")

    def handle_deleted(self, path: Path) -> IncrementalUpdateResult:
        if not self._is_supported(path):
            return self._skipped_result(path=path, event_type="deleted", detail="unsupported file type")
        if self._is_debounced(path):
            return self._skipped_result(path=path, event_type="deleted", detail="debounced")
        if not self._is_under_kb_dir(path):
            logger.debug("Deleted file event ignored because file is outside watch path: %s", path)
            return self._skipped_result(path=path, event_type="deleted", detail="outside watch path")

        descriptor = self._build_descriptor(path)
        deleted = self._collection.replace_document(
            doc_id=descriptor.doc_id,
            ids=[],
            documents=[],
            metadatas=[],
            embeddings=[],
        ).deleted
        self._hash_store.remove(descriptor.source)
        logger.info(
            "Deleted file event processed: source=%s doc_id=%s deleted_chunks=%s",
            descriptor.source,
            descriptor.doc_id,
            deleted,
        )
        return IncrementalUpdateResult(
            descriptor=descriptor,
            event_type="deleted",
            status="deleted",
            chunks_deleted=deleted,
        )

    def _handle_upsert(self, path: Path, event_type: str, *, bypass_debounce: bool = False) -> IncrementalUpdateResult:
        if not self._is_supported(path):
            return self._skipped_result(path=path, event_type=event_type, detail="unsupported file type")
        if not bypass_debounce and self._is_debounced(path):
            return self._skipped_result(path=path, event_type=event_type, detail="debounced")
        if not path.exists():
            logger.debug("Watcher event ignored because file no longer exists: %s", path)
            return self._skipped_result(path=path, event_type=event_type, detail="file no longer exists")
        if not self._is_under_kb_dir(path):
            logger.debug("Watcher event ignored because file is outside watch path: %s", path)
            return self._skipped_result(path=path, event_type=event_type, detail="outside watch path")

        self._clear_readonly_media_attribute(path)
        descriptor = self._build_descriptor(path)
        readable_error = self._readability_error(path)
        if readable_error is not None:
            self._hash_store.mark_failed(descriptor.source, descriptor.doc_id, readable_error)
            return IncrementalUpdateResult(
                descriptor=descriptor,
                event_type=event_type,
                status="failed",
                detail=readable_error,
            )
        try:
            content_hash = self._compute_hash(path)
        except (OSError, PermissionError, FileNotFoundError) as exc:
            detail = f"file is not readable: {exc}"
            self._hash_store.mark_failed(descriptor.source, descriptor.doc_id, detail)
            return IncrementalUpdateResult(
                descriptor=descriptor,
                event_type=event_type,
                status="failed",
                detail=detail,
            )
        stored = self._hash_store.get(descriptor.source)
        if stored and stored.get("content_hash") == content_hash:
            if not self._needs_media_transcript_retry(path, stored):
                logger.debug(
                    "Hash unchanged, skipping rebuild: event=%s source=%s doc_id=%s",
                    event_type,
                    descriptor.source,
                    descriptor.doc_id,
                )
                return IncrementalUpdateResult(
                    descriptor=descriptor,
                    event_type=event_type,
                    status="skipped",
                    detail="content hash unchanged",
                )
            logger.info(
                "Media transcript needs retry: source=%s stored_status=%s stored_provider=%s",
                descriptor.source,
                stored.get("transcript_status"),
                stored.get("transcript_provider"),
            )

        if self._is_media_file(path):
            self._hash_store.set(
                source_path=descriptor.source,
                doc_id=descriptor.doc_id,
                content_hash=content_hash,
                transcript_status="transcribing",
                transcript_provider="",
                transcript_error="",
            )

        try:
            payload = build_payload_for_source(descriptor=descriptor, registry=self._loader_registry)
            embeddings = self._embedder.embed_texts(payload.documents) if payload.documents else []
            replaced = self._collection.replace_document(
                doc_id=payload.doc_id,
                ids=payload.ids,
                documents=payload.documents,
                metadatas=payload.metadatas,
                embeddings=embeddings,
            )
            ts = _derive_transcript_status_from_payload(payload)
            self._hash_store.set(
                source_path=payload.descriptor.source,
                doc_id=payload.doc_id,
                content_hash=content_hash,
                transcript_status=ts.get("transcript_status", ""),
                transcript_provider=ts.get("transcript_provider", ""),
                transcript_error=ts.get("transcript_error", ""),
            )
        except Exception as exc:
            logger.exception(
                "Incremental rebuild failed; existing chunks preserved: event=%s source=%s doc_id=%s",
                event_type,
                descriptor.source,
                descriptor.doc_id,
            )
            self._hash_store.set(
                source_path=descriptor.source,
                doc_id=descriptor.doc_id,
                content_hash=content_hash,
                status="failed",
                error=str(exc),
                transcript_status="failed",
                transcript_provider="",
                transcript_error=str(exc),
            )
            return IncrementalUpdateResult(
                descriptor=descriptor,
                event_type=event_type,
                status="failed",
                detail=f"existing chunks preserved after rebuild failure: {exc}",
            )

        logger.info(
            "Incremental rebuild completed: event=%s source=%s doc_id=%s hash_changed=true deleted_chunks=%s rebuilt_chunks=%s current_chunks=%s transcript_status=%s",
            event_type,
            payload.descriptor.source,
            payload.doc_id,
            replaced.deleted,
            replaced.upserted,
            self._count_document_chunks(payload.doc_id),
            ts.get("transcript_status", ""),
        )
        return IncrementalUpdateResult(
            descriptor=payload.descriptor,
            event_type=event_type,
            status="updated",
            chunks_upserted=replaced.upserted,
            chunks_deleted=replaced.deleted,
        )

    def _build_descriptor(self, path: Path):
        return build_file_descriptor(path.resolve(), self._kb_dir)

    def _skipped_result(self, *, path: Path, event_type: str, detail: str) -> IncrementalUpdateResult:
        descriptor = self._build_descriptor(path) if self._is_under_kb_dir(path) else build_file_descriptor(path.resolve(), path.resolve().parent)
        return IncrementalUpdateResult(
            descriptor=descriptor,
            event_type=event_type,
            status="skipped",
            detail=detail,
        )

    def _is_supported(self, path: Path) -> bool:
        return path.suffix.lower() in SUPPORTED_EXTENSIONS and not is_media_sidecar_transcript(path)

    def _is_under_kb_dir(self, path: Path) -> bool:
        try:
            path.resolve().relative_to(self._kb_dir)
            return True
        except ValueError:
            return False

    def _compute_hash(self, path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def _is_media_file(self, path: Path) -> bool:
        return path.suffix.lower() in MEDIA_EXTENSIONS

    def _clear_readonly_media_attribute(self, path: Path) -> None:
        if not self._is_media_file(path) or not self._is_under_kb_dir(path):
            return

        try:
            current_mode = path.stat().st_mode
        except (OSError, PermissionError, FileNotFoundError) as exc:
            logger.warning("Could not inspect media file attributes: %s (%s)", path.name, exc)
            return

        if current_mode & stat.S_IWRITE:
            return

        try:
            path.chmod(current_mode | stat.S_IWRITE)
            logger.info("Media file was read-only; cleared read-only attribute: %s", path.name)
        except (OSError, PermissionError) as exc:
            logger.warning(
                "Media file was read-only but clearing the read-only attribute failed: %s (%s)",
                path.name,
                exc,
            )

    def _needs_media_transcript_retry(self, path: Path, stored: dict[str, Any]) -> bool:
        """Return True if a media file needs re-transcription despite unchanged hash.

        Retry conditions:
        - Previous transcript_status is not 'ready' (failed, empty, or unknown)
        - Previous transcript_provider differs from current effective provider
        """
        if not self._is_media_file(path):
            return False
        ts = stored.get("transcript_status", "")
        if not ts:
            # No transcript status recorded yet — this media file was likely
            # ingested before transcript_status tracking was added, or the
            # provider was mock/disabled at the time.
            return True
        if ts != "ready":
            return True
        stored_provider = stored.get("transcript_provider", "")
        current_provider = _get_current_transcript_provider()
        if stored_provider and current_provider and stored_provider != current_provider:
            return True
        return False

    def _readability_error(self, path: Path) -> str | None:
        try:
            if not path.exists():
                return "file no longer exists"
            if not path.is_file():
                return "path is not a file"
            path.stat()
            with path.open("rb") as handle:
                handle.read(1)
        except (OSError, PermissionError, FileNotFoundError) as exc:
            return f"file is not readable: {exc}"
        return None

    def _is_debounced(self, path: Path) -> bool:
        now = time.monotonic()
        key = str(path.resolve())
        previous = self._last_seen.get(key)
        if previous is not None and now - previous < self._debounce_seconds:
            logger.debug(
                "Watcher event ignored by debounce: path=%s debounce_seconds=%s",
                key,
                self._debounce_seconds,
            )
            return True

        self._last_seen[key] = now
        return False


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_current_transcript_provider() -> str:
    """Return the effective transcript provider without triggering transcription."""
    try:
        from app.rag.media_loader import _resolve_media_transcript_runtime_config

        resolved = _resolve_media_transcript_runtime_config()
        if not resolved.enabled:
            return "disabled"
        return resolved.provider
    except Exception:
        return ""


def _derive_transcript_status_from_payload(payload) -> dict[str, str]:
    """Extract transcript status fields from a DocumentPayload's chunk metadata.

    Returns a dict with transcript_status, transcript_provider, transcript_error.
    """
    metadatas = payload.metadatas if payload.metadatas else []
    if not metadatas:
        return {}

    first = metadatas[0]
    loader_name = str(first.get("loader_name", ""))
    if loader_name not in ("audio.transcribe", "video.transcribe"):
        return {}

    provider = str(first.get("transcript_provider", ""))
    warnings_str = str(first.get("loader_warnings", ""))
    warnings = [w.strip() for w in warnings_str.split(",") if w.strip()]

    has_text = bool(payload.documents and any(d.strip() for d in payload.documents))

    if provider in ("mock", "disabled") or "transcript_mock_fallback" in warnings:
        return {
            "transcript_status": "skipped",
            "transcript_provider": provider,
            "transcript_error": "Transcript was not generated (mock/disabled provider).",
        }

    if "transcript_empty" in warnings or not has_text:
        return {
            "transcript_status": "failed",
            "transcript_provider": provider,
            "transcript_error": "Transcription produced empty text.",
        }

    return {
        "transcript_status": "ready",
        "transcript_provider": provider,
        "transcript_error": "",
    }
