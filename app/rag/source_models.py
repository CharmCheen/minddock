"""Formal source and ingest domain models."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

try:
    from langchain_core.documents import Document
except ModuleNotFoundError:  # pragma: no cover - optional dependency fallback
    @dataclass(frozen=True)
    class Document:
        """Minimal fallback document type for environments without langchain_core."""

        page_content: str
        metadata: dict[str, object] = field(default_factory=dict)


def utc_now_iso() -> str:
    """Return an ISO-8601 UTC timestamp without microseconds."""

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class SourceDescriptor:
    """Stable descriptor for an ingestable source."""

    source: str
    source_type: str
    local_path: Path | None = None
    requested_source: str | None = None

    @property
    def doc_id(self) -> str:
        return hashlib.sha1(self.source.encode("utf-8")).hexdigest()

    @property
    def source_path(self) -> str:
        return self.source

    @property
    def display_name(self) -> str:
        return self.source


@dataclass(frozen=True)
class SourceLoadResult:
    """Normalized text and metadata returned by a source loader."""

    descriptor: SourceDescriptor
    title: str
    text: str
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class CatalogQuery:
    """Simple query options for source catalog listing."""

    source_type: str | None = None


@dataclass(frozen=True)
class SourceState:
    """Current source lifecycle state derived from indexed chunk metadata."""

    doc_id: str
    source: str
    current_version: str | None = None
    content_hash: str | None = None
    last_ingested_at: str | None = None
    chunk_count: int = 0
    ingest_status: str | None = None


@dataclass(frozen=True)
class SourceCatalogEntry:
    """Aggregated source-level view derived from stored chunk metadata."""

    doc_id: str
    source: str
    source_type: str
    title: str
    chunk_count: int
    sections: tuple[str, ...] = ()
    pages: tuple[int, ...] = ()
    requested_url: str | None = None
    final_url: str | None = None
    state: SourceState | None = None
    # Enrichment fields — populated from chunk metadata where available
    domain: str | None = None  # URL sources: netloc (e.g. "arxiv.org"); file sources: None
    description: str | None = None  # URL sources: og_description; file sources: None


@dataclass(frozen=True)
class SourceDetail:
    """Detailed source view including representative metadata."""

    entry: SourceCatalogEntry
    representative_metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class SourceChunkPreview:
    """Readable preview for one stored chunk within a source."""

    chunk_id: str
    chunk_index: int | None
    preview_text: str
    title: str
    section: str | None = None
    location: str | None = None
    ref: str | None = None
    page: int | None = None
    anchor: str | None = None
    admin_metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class SourceChunkPage:
    """Paginated chunk preview page for one source."""

    total_chunks: int
    returned_chunks: int
    limit: int
    offset: int
    chunks: list[SourceChunkPreview] = field(default_factory=list)


@dataclass(frozen=True)
class SourceInspectResult:
    """Source summary plus paginated chunk previews."""

    detail: SourceDetail
    chunk_page: SourceChunkPage
    include_admin_metadata: bool = False
    admin_metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class DocumentPayload:
    """Normalized document payload ready for vector-store replacement."""

    descriptor: SourceDescriptor
    ids: list[str]
    documents: list[str]
    metadatas: list[dict[str, str]]

    @property
    def doc_id(self) -> str:
        return self.descriptor.doc_id

    @property
    def source_path(self) -> str:
        return self.descriptor.source_path

    @classmethod
    def empty(cls, descriptor: SourceDescriptor) -> "DocumentPayload":
        return cls(descriptor=descriptor, ids=[], documents=[], metadatas=[])

    @classmethod
    def from_documents(cls, descriptor: SourceDescriptor, documents: list[Document]) -> "DocumentPayload":
        return cls(
            descriptor=descriptor,
            ids=[str(doc.metadata.get("chunk_id", "")) for doc in documents],
            documents=[doc.page_content for doc in documents],
            metadatas=[dict(doc.metadata) for doc in documents],
        )

    def to_legacy_dict(self) -> dict[str, object]:
        return {
            "doc_id": self.doc_id,
            "source_path": self.source_path,
            "ids": list(self.ids),
            "documents": list(self.documents),
            "metadatas": list(self.metadatas),
        }


@dataclass(frozen=True)
class ReplaceDocumentResult:
    """Result of replacing one source's chunks in the vector store."""

    upserted: int
    deleted: int


@dataclass(frozen=True)
class DeleteSourceResult:
    """Structured outcome for deleting one indexed source."""

    found: bool
    doc_id: str | None = None
    source: str | None = None
    source_type: str | None = None
    deleted_chunks: int = 0


@dataclass(frozen=True)
class FailedSourceInfo:
    """Failure information for one source without aborting the whole batch."""

    source: str
    source_type: str
    reason: str

    def to_api_dict(self) -> dict[str, str]:
        return {
            "source": self.source,
            "source_type": self.source_type,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class IngestSourceResult:
    """Structured outcome for one source processed by batch ingest."""

    descriptor: SourceDescriptor
    ok: bool
    chunks_upserted: int = 0
    chunks_deleted: int = 0
    failure: FailedSourceInfo | None = None


@dataclass(frozen=True)
class IngestBatchResult:
    """Structured outcome for a batch ingest request."""

    source_results: list[IngestSourceResult]

    @property
    def documents(self) -> int:
        return sum(1 for item in self.source_results if item.ok)

    @property
    def chunks(self) -> int:
        return sum(item.chunks_upserted for item in self.source_results)

    @property
    def ingested_sources(self) -> list[str]:
        return [item.descriptor.source for item in self.source_results if item.ok]

    @property
    def failed_sources(self) -> list[FailedSourceInfo]:
        return [item.failure for item in self.source_results if item.failure is not None]

    def all_failed(self) -> bool:
        return bool(self.source_results) and self.documents == 0

    def to_api_dict(self) -> dict[str, object]:
        return {
            "documents": self.documents,
            "chunks": self.chunks,
            "ingested_sources": self.ingested_sources,
            "failed_sources": [failure.to_api_dict() for failure in self.failed_sources],
        }


@dataclass(frozen=True)
class IncrementalUpdateResult:
    """Structured outcome for a watcher/incremental event."""

    descriptor: SourceDescriptor
    event_type: str
    status: str
    chunks_upserted: int = 0
    chunks_deleted: int = 0
    detail: str = ""
