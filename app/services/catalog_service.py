"""Source catalog and lifecycle management services."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from app.core.config import get_settings
from app.rag.source_loader import build_file_descriptor, build_url_descriptor
from app.rag.source_models import CatalogQuery, DeleteSourceResult, SourceCatalogEntry, SourceDetail, SourceInspectResult, SourceState
from app.rag.vectorstore import get_vectorstore, inspect_source, list_source_details
from app.services.ingest_service import IngestService
from app.stores.ingestion_status_store import IngestionStatusRecord, get_all, write_ready
from app.services.service_models import (
    CatalogServiceResult,
    DeleteSourceServiceResult,
    ReingestSourceServiceResult,
    ServiceIssue,
    SourceDetailServiceResult,
    SourceInspectServiceResult,
    SourceStats,
    UseCaseMetadata,
    UseCaseTiming,
)

logger = logging.getLogger(__name__)


class CatalogService:
    """Manage indexed source lifecycle without introducing a separate catalog database."""

    def __init__(self, *, settings=None, collection=None, ingest_service: IngestService | None = None) -> None:
        self._settings = settings or get_settings()
        self._collection = collection or get_vectorstore()
        self._ingest_service = ingest_service or IngestService(settings=self._settings, collection=self._collection)

    def list_sources(self, source_type: str | None = None) -> CatalogServiceResult:
        started = time.perf_counter()
        details = self._list_details(source_type=source_type)
        chroma_entries = [detail.entry for detail in details]
        chroma_identity_keys: set[str] = set()
        for entry in chroma_entries:
            chroma_identity_keys.update(self._entry_identity_keys(entry))

        # Append indexing/failed records not yet in Chroma
        extra_entries: list[SourceCatalogEntry] = []
        for rec in get_all():
            if self._status_record_identity_keys(rec) & chroma_identity_keys:
                continue
            if source_type is not None and rec.source_type != source_type:
                continue
            extra_entries.append(self._entry_from_status_record(rec).entry)

        all_entries = [*chroma_entries, *extra_entries]
        return CatalogServiceResult(
            entries=all_entries,
            metadata=UseCaseMetadata(
                empty_result=not all_entries,
                warnings=("No indexed sources found.",) if not all_entries else (),
                issues=(
                    ServiceIssue(code="empty_result", message="No indexed sources found.", severity="info"),
                )
                if not all_entries
                else (),
                filter_applied=source_type is not None,
                source_stats=SourceStats(
                    requested_sources=len(all_entries),
                    succeeded_sources=len(chroma_entries),
                    failed_sources=len(extra_entries),
                ),
                timing=UseCaseTiming(total_ms=round((time.perf_counter() - started) * 1000, 2)),
            ),
        )

    def get_source_detail(
        self,
        *,
        doc_id: str | None = None,
        source: str | None = None,
        include_admin_metadata: bool = False,
    ) -> SourceDetailServiceResult:
        started = time.perf_counter()
        detail = self._resolve_detail(doc_id=doc_id, source=source) or self._resolve_status_detail(doc_id=doc_id, source=source)
        found = detail is not None
        admin_metadata = self._build_source_admin_metadata(detail) if include_admin_metadata and detail is not None else {}
        return SourceDetailServiceResult(
            found=found,
            detail=detail,
            metadata=UseCaseMetadata(
                empty_result=not found,
                warnings=("Requested source was not found.",) if not found else (),
                issues=(
                    ServiceIssue(code="source_not_found", message="Requested source was not found.", severity="info"),
                )
                if not found
                else (),
                timing=UseCaseTiming(total_ms=round((time.perf_counter() - started) * 1000, 2)),
            ),
            include_admin_metadata=include_admin_metadata,
            admin_metadata=admin_metadata,
        )

    def inspect_source(
        self,
        *,
        doc_id: str | None = None,
        source: str | None = None,
        limit: int = 10,
        offset: int = 0,
        include_admin_metadata: bool = False,
    ) -> SourceInspectServiceResult:
        started = time.perf_counter()
        effective_limit = max(1, limit)
        effective_offset = max(0, offset)
        warnings: tuple[str, ...] = ()
        issues: tuple[ServiceIssue, ...] = ()
        if effective_limit != limit or effective_offset != offset:
            warnings = ("Invalid paging parameters were normalized for source inspection.",)
            issues = (
                ServiceIssue(
                    code="invalid_paging_normalized",
                    message="Invalid paging parameters were normalized for source inspection.",
                    severity="info",
                ),
            )
        detail = self._resolve_detail(doc_id=doc_id, source=source)
        if detail is None:
            return SourceInspectServiceResult(
                found=False,
                inspect=None,
                metadata=UseCaseMetadata(
                    empty_result=True,
                    warnings=warnings + ("Requested source was not found.",),
                    issues=issues + (ServiceIssue(code="source_not_found", message="Requested source was not found.", severity="info"),),
                    timing=UseCaseTiming(total_ms=round((time.perf_counter() - started) * 1000, 2)),
                ),
            )

        inspect_result = self._inspect_doc_id(
            detail.entry.doc_id,
            limit=effective_limit,
            offset=effective_offset,
            include_admin_metadata=include_admin_metadata,
        )
        if inspect_result is None:
            return SourceInspectServiceResult(
                found=False,
                inspect=None,
                metadata=UseCaseMetadata(
                    empty_result=True,
                    warnings=warnings + ("Requested source was not found.",),
                    issues=issues + (ServiceIssue(code="source_not_found", message="Requested source was not found.", severity="info"),),
                    timing=UseCaseTiming(total_ms=round((time.perf_counter() - started) * 1000, 2)),
                ),
            )

        empty_page = inspect_result.chunk_page.returned_chunks == 0
        if empty_page and inspect_result.chunk_page.total_chunks > 0:
            warnings = warnings + ("Requested chunk page is empty for the current offset.",)
            issues = issues + (ServiceIssue(code="chunk_page_empty", message="Requested chunk page is empty for the current offset.", severity="info"),)

        return SourceInspectServiceResult(
            found=True,
            inspect=inspect_result,
            metadata=UseCaseMetadata(
                empty_result=empty_page,
                warnings=warnings,
                issues=issues,
                timing=UseCaseTiming(total_ms=round((time.perf_counter() - started) * 1000, 2)),
            ),
        )

    def delete_source(self, *, doc_id: str | None = None, source: str | None = None) -> DeleteSourceServiceResult:
        started = time.perf_counter()
        detail = self._resolve_detail(doc_id=doc_id, source=source) or self._resolve_status_detail(doc_id=doc_id, source=source)
        if detail is None:
            return DeleteSourceServiceResult(
                result=DeleteSourceResult(found=False),
                metadata=UseCaseMetadata(
                    warnings=("Requested source was not found.",),
                    issues=(ServiceIssue(code="source_not_found", message="Requested source was not found.", severity="info"),),
                    timing=UseCaseTiming(total_ms=round((time.perf_counter() - started) * 1000, 2)),
                ),
            )

        # Clean up any status store record so the source doesn't linger as "indexing"/"failed"
        write_ready(doc_id=detail.entry.doc_id)

        deleted = self._collection.delete_document(detail.entry.doc_id)
        logger.info(
            "Source deleted from catalog: source=%s doc_id=%s deleted_chunks=%d",
            detail.entry.source,
            detail.entry.doc_id,
            deleted,
        )
        return DeleteSourceServiceResult(
            result=DeleteSourceResult(
                found=True,
                doc_id=detail.entry.doc_id,
                source=detail.entry.source,
                source_type=detail.entry.source_type,
                deleted_chunks=deleted,
            ),
            metadata=UseCaseMetadata(
                timing=UseCaseTiming(total_ms=round((time.perf_counter() - started) * 1000, 2)),
                source_stats=SourceStats(requested_sources=1, succeeded_sources=1, failed_sources=0),
            ),
        )

    def reingest_source(self, *, doc_id: str | None = None, source: str | None = None) -> ReingestSourceServiceResult:
        started = time.perf_counter()
        detail = self._resolve_detail(doc_id=doc_id, source=source) or self._resolve_status_detail(doc_id=doc_id, source=source)
        if detail is None and not source:
            return ReingestSourceServiceResult(
                found=False,
                source_result=None,
                metadata=UseCaseMetadata(
                    warnings=("Requested source was not found.",),
                    issues=(ServiceIssue(code="source_not_found", message="Requested source was not found.", severity="info"),),
                    timing=UseCaseTiming(total_ms=round((time.perf_counter() - started) * 1000, 2)),
                ),
            )

        descriptor = self._build_descriptor_for_entry(detail.entry) if detail is not None else self._build_descriptor_from_source(source or "")
        source_result = self._ingest_service.ingest_descriptor(descriptor)
        warnings: tuple[str, ...] = ()
        issues: tuple[ServiceIssue, ...] = ()
        debug_notes: tuple[str, ...] = ()
        if detail is None:
            debug_notes = ("reingest executed from explicit source rather than existing catalog entry",)
        if not source_result.ok and source_result.failure is not None:
            warnings = (f"Reingest failed for {source_result.descriptor.source}.",)
            issues = (
                ServiceIssue(
                    code="source_reingest_failed",
                    message=source_result.failure.reason,
                    severity="warning",
                    source=source_result.descriptor.source,
                ),
            )

        return ReingestSourceServiceResult(
            found=True,
            source_result=source_result,
            metadata=UseCaseMetadata(
                partial_failure=not source_result.ok,
                warnings=warnings,
                issues=issues,
                timing=UseCaseTiming(total_ms=round((time.perf_counter() - started) * 1000, 2)),
                source_stats=SourceStats(requested_sources=1, succeeded_sources=1 if source_result.ok else 0, failed_sources=0 if source_result.ok else 1),
                debug_notes=debug_notes,
            ),
        )

    def _list_details(self, *, source_type: str | None = None) -> list[SourceDetail]:
        if hasattr(self._collection, "list_source_details"):
            return self._collection.list_source_details(CatalogQuery(source_type=source_type))
        return list_source_details(CatalogQuery(source_type=source_type))

    def _resolve_detail(self, *, doc_id: str | None = None, source: str | None = None) -> SourceDetail | None:
        normalized_doc_id = (doc_id or "").strip()
        normalized_source = (source or "").strip()
        for detail in self._list_details():
            if normalized_doc_id and detail.entry.doc_id == normalized_doc_id:
                return detail
            if normalized_source and detail.entry.source == normalized_source:
                return detail
        return None

    def _resolve_status_detail(self, *, doc_id: str | None = None, source: str | None = None) -> SourceDetail | None:
        lookup_keys = self._identity_keys_for_values((doc_id, source))
        if not lookup_keys:
            return None
        for rec in get_all():
            if lookup_keys & self._status_record_identity_keys(rec):
                return self._entry_from_status_record(rec)
        return None

    def _entry_from_status_record(self, rec: IngestionStatusRecord) -> SourceDetail:
        state = SourceState(
            doc_id=rec.doc_id,
            source=rec.requested_url,
            current_version=None,
            content_hash=None,
            last_ingested_at=None,
            chunk_count=0,
            ingest_status=rec.status,
            error_message=rec.error_message,
        )
        entry = SourceCatalogEntry(
            doc_id=rec.doc_id,
            source=rec.requested_url,
            source_type=rec.source_type,
            title=rec.requested_url,
            chunk_count=0,
            sections=(),
            pages=(),
            requested_url=rec.requested_url if rec.source_type == "url" else None,
            final_url=None,
            state=state,
            domain=None,
            description=rec.error_message,
        )
        return SourceDetail(entry=entry, representative_metadata={"source": rec.requested_url, "status": rec.status})

    def _entry_identity_keys(self, entry: SourceCatalogEntry) -> set[str]:
        values: list[str | None] = [
            entry.doc_id,
            entry.source,
            entry.requested_url,
            entry.final_url,
        ]
        if entry.state is not None:
            values.extend([entry.state.doc_id, entry.state.source])
        return self._identity_keys_for_values(values)

    def _status_record_identity_keys(self, rec: IngestionStatusRecord) -> set[str]:
        return self._identity_keys_for_values((rec.doc_id, rec.requested_url))

    def _identity_keys_for_values(self, values: tuple[str | None, ...] | list[str | None]) -> set[str]:
        keys: set[str] = set()
        for value in values:
            if not value:
                continue
            stripped = value.strip()
            if not stripped:
                continue
            keys.add(stripped)
            keys.add(self._normalize_url_key(stripped))
        return {key for key in keys if key}

    def _normalize_url_key(self, value: str) -> str:
        try:
            parsed = urlsplit(value)
        except ValueError:
            return value.rstrip("/")
        if not parsed.scheme or not parsed.netloc:
            return value.rstrip("/")
        path = parsed.path.rstrip("/")
        return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, parsed.query, ""))

    def _inspect_doc_id(
        self,
        doc_id: str,
        *,
        limit: int,
        offset: int,
        include_admin_metadata: bool,
    ) -> SourceInspectResult | None:
        if hasattr(self._collection, "inspect_source"):
            return self._collection.inspect_source(
                doc_id,
                limit=limit,
                offset=offset,
                include_admin_metadata=include_admin_metadata,
            )
        return inspect_source(
            doc_id,
            limit=limit,
            offset=offset,
            include_admin_metadata=include_admin_metadata,
        )

    def _build_descriptor_for_entry(self, entry: SourceCatalogEntry):
        if entry.source_type == "file":
            kb_dir = Path(self._settings.kb_dir)
            return build_file_descriptor((kb_dir / entry.source).resolve(), kb_dir.resolve())
        if entry.source_type == "url":
            return build_url_descriptor(entry.source)
        raise ValueError(f"Unsupported source type for reingest: {entry.source_type}")

    def _build_descriptor_from_source(self, source: str):
        normalized = source.strip()
        if normalized.startswith("http://") or normalized.startswith("https://"):
            return build_url_descriptor(normalized)
        kb_dir = Path(self._settings.kb_dir).resolve()
        return build_file_descriptor((kb_dir / normalized).resolve(), kb_dir)

    def _build_source_admin_metadata(self, detail: SourceDetail) -> dict[str, object]:
        entry = detail.entry
        metadata = {
            "doc_id": entry.doc_id,
            "source": entry.source,
            "source_type": entry.source_type,
            "chunk_count": entry.chunk_count,
            "representative_metadata": detail.representative_metadata,
        }
        if entry.requested_url:
            metadata["requested_url"] = entry.requested_url
        if entry.final_url:
            metadata["final_url"] = entry.final_url
        return metadata
