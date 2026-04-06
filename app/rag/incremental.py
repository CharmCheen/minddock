"""Incremental document ingestion with debounce and hash checking."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Protocol

from app.core.config import get_settings
from app.rag.embeddings import EmbeddingBackend, get_embedding_backend
from app.rag.ingest import SUPPORTED_EXTENSIONS, build_payload_for_source
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

    def _load(self) -> dict[str, dict[str, str]]:
        if not self._path.exists():
            return {}
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            logger.warning("Hash store is invalid, starting from empty store: %s", self._path)
            return {}

    def save(self) -> None:
        self._path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get(self, source_path: str) -> dict[str, str] | None:
        return self._data.get(source_path)

    def set(self, source_path: str, doc_id: str, content_hash: str) -> None:
        self._data[source_path] = {"doc_id": doc_id, "content_hash": content_hash}
        self.save()

    def remove(self, source_path: str) -> None:
        if source_path in self._data:
            del self._data[source_path]
            self.save()


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

    def _handle_upsert(self, path: Path, event_type: str) -> IncrementalUpdateResult:
        if not self._is_supported(path):
            return self._skipped_result(path=path, event_type=event_type, detail="unsupported file type")
        if self._is_debounced(path):
            return self._skipped_result(path=path, event_type=event_type, detail="debounced")
        if not path.exists():
            logger.debug("Watcher event ignored because file no longer exists: %s", path)
            return self._skipped_result(path=path, event_type=event_type, detail="file no longer exists")
        if not self._is_under_kb_dir(path):
            logger.debug("Watcher event ignored because file is outside watch path: %s", path)
            return self._skipped_result(path=path, event_type=event_type, detail="outside watch path")

        descriptor = self._build_descriptor(path)
        content_hash = self._compute_hash(path)
        stored = self._hash_store.get(descriptor.source)
        if stored and stored.get("content_hash") == content_hash:
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
            self._hash_store.set(source_path=payload.descriptor.source, doc_id=payload.doc_id, content_hash=content_hash)
        except Exception:
            logger.exception(
                "Incremental rebuild failed; existing chunks preserved: event=%s source=%s doc_id=%s",
                event_type,
                descriptor.source,
                descriptor.doc_id,
            )
            return IncrementalUpdateResult(
                descriptor=descriptor,
                event_type=event_type,
                status="failed",
                detail="existing chunks preserved after rebuild failure",
            )

        logger.info(
            "Incremental rebuild completed: event=%s source=%s doc_id=%s hash_changed=true deleted_chunks=%s rebuilt_chunks=%s current_chunks=%s",
            event_type,
            payload.descriptor.source,
            payload.doc_id,
            replaced.deleted,
            replaced.upserted,
            self._count_document_chunks(payload.doc_id),
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
        return path.suffix.lower() in SUPPORTED_EXTENSIONS

    def _is_under_kb_dir(self, path: Path) -> bool:
        try:
            path.resolve().relative_to(self._kb_dir)
            return True
        except ValueError:
            return False

    def _compute_hash(self, path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

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
