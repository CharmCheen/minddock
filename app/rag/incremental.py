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
from app.rag.ingest import SUPPORTED_EXTENSIONS, build_doc_id, build_document_payload
from app.rag.vectorstore import count_document_chunks, delete_document, get_vectorstore

logger = logging.getLogger(__name__)


class VectorCollection(Protocol):
    """Minimal collection protocol used by incremental ingest."""

    def upsert(
        self,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict[str, str]],
        embeddings: list[list[float]],
    ) -> None:
        """Insert or update chunk records."""


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
        embedder: EmbeddingBackend | None = None,
        collection: VectorCollection | None = None,
        delete_document_fn=delete_document,
        count_document_chunks_fn=count_document_chunks,
    ) -> None:
        settings = get_settings()
        self._kb_dir = (kb_dir or Path(settings.watch_path)).resolve()
        self._debounce_seconds = (
            settings.watch_debounce_seconds if debounce_seconds is None else debounce_seconds
        )
        self._hash_store = hash_store or HashStore(Path(settings.hash_store_path))
        self._embedder = embedder or get_embedding_backend(settings.embedding_model)
        self._collection = collection or get_vectorstore()
        self._delete_document = delete_document_fn
        self._count_document_chunks = count_document_chunks_fn
        self._last_seen: dict[str, float] = {}

    def handle_created(self, path: Path) -> None:
        self._handle_upsert(path=path, event_type="created")

    def handle_modified(self, path: Path) -> None:
        self._handle_upsert(path=path, event_type="modified")

    def handle_deleted(self, path: Path) -> None:
        if not self._is_supported(path):
            return
        if self._is_debounced(path):
            return
        if not self._is_under_kb_dir(path):
            logger.debug("Deleted file event ignored because file is outside watch path: %s", path)
            return

        source_path = self._relative_source_path(path)
        doc_id = build_doc_id(Path(source_path))
        deleted = self._delete_document(doc_id)
        self._hash_store.remove(source_path)
        logger.info(
            "Deleted file event processed: source=%s doc_id=%s deleted_chunks=%s",
            source_path,
            doc_id,
            deleted,
        )

    def _handle_upsert(self, path: Path, event_type: str) -> None:
        if not self._is_supported(path):
            return
        if self._is_debounced(path):
            return
        if not path.exists():
            logger.debug("Watcher event ignored because file no longer exists: %s", path)
            return
        if not self._is_under_kb_dir(path):
            logger.debug("Watcher event ignored because file is outside watch path: %s", path)
            return

        source_path = self._relative_source_path(path)
        doc_id = build_doc_id(Path(source_path))
        content_hash = self._compute_hash(path)
        stored = self._hash_store.get(source_path)
        if stored and stored.get("content_hash") == content_hash:
            logger.debug(
                "Hash unchanged, skipping rebuild: event=%s source=%s doc_id=%s",
                event_type,
                source_path,
                doc_id,
            )
            return

        previous_chunks = self._delete_document(doc_id)
        payload = build_document_payload(path=path, kb_dir=self._kb_dir)
        documents = payload["documents"]
        if documents:
            embeddings = self._embedder.embed_texts(documents)
            self._collection.upsert(
                ids=payload["ids"],
                documents=documents,
                metadatas=payload["metadatas"],
                embeddings=embeddings,
            )

        self._hash_store.set(source_path=source_path, doc_id=doc_id, content_hash=content_hash)
        logger.info(
            "Incremental rebuild completed: event=%s source=%s doc_id=%s hash_changed=true deleted_chunks=%s rebuilt_chunks=%s current_chunks=%s",
            event_type,
            source_path,
            doc_id,
            previous_chunks,
            len(documents),
            self._count_document_chunks(doc_id),
        )

    def _is_supported(self, path: Path) -> bool:
        return path.suffix.lower() in SUPPORTED_EXTENSIONS

    def _is_under_kb_dir(self, path: Path) -> bool:
        try:
            path.resolve().relative_to(self._kb_dir)
            return True
        except ValueError:
            return False

    def _relative_source_path(self, path: Path) -> str:
        return path.resolve().relative_to(self._kb_dir).as_posix()

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
