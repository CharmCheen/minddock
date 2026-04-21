"""Source catalog and lifecycle management services."""

from __future__ import annotations

import logging
import time
from pathlib import Path

from app.core.config import get_settings
from app.rag.source_loader import build_file_descriptor, build_url_descriptor
from app.rag.source_models import CatalogQuery, DeleteSourceResult, SourceCatalogEntry, SourceDetail, SourceInspectResult
from app.rag.vectorstore import get_vectorstore, inspect_source, list_source_details
from app.services.ingest_service import IngestService
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
        entries = [detail.entry for detail in self._list_details(source_type=source_type)]
        return CatalogServiceResult(
            entries=entries,
            metadata=UseCaseMetadata(
                empty_result=not entries,
                warnings=("No indexed sources found.",) if not entries else (),
                issues=(
                    ServiceIssue(code="empty_result", message="No indexed sources found.", severity="info"),
                )
                if not entries
                else (),
                filter_applied=source_type is not None,
                source_stats=SourceStats(
                    requested_sources=len(entries),
                    succeeded_sources=len(entries),
                    failed_sources=0,
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
        detail = self._resolve_detail(doc_id=doc_id, source=source)
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
        detail = self._resolve_detail(doc_id=doc_id, source=source)
        if detail is None:
            return DeleteSourceServiceResult(
                result=DeleteSourceResult(found=False),
                metadata=UseCaseMetadata(
                    warnings=("Requested source was not found.",),
                    issues=(ServiceIssue(code="source_not_found", message="Requested source was not found.", severity="info"),),
                    timing=UseCaseTiming(total_ms=round((time.perf_counter() - started) * 1000, 2)),
                ),
            )

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
        detail = self._resolve_detail(doc_id=doc_id, source=source)
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
