"""Query-time source participation projection helpers."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace
from typing import TYPE_CHECKING

from app.rag.retrieval_models import CitationRecord
from app.rag.source_models import SourceCatalogEntry, SourceParticipationState

if TYPE_CHECKING:
    from app.services.catalog_service import CatalogService


def extract_participating_doc_ids(citations: Iterable[CitationRecord]) -> frozenset[str]:
    """Collect the unique doc_ids cited by the current response."""

    return frozenset(citation.doc_id for citation in citations if citation.doc_id)


def project_source_participation(
    entries: Iterable[SourceCatalogEntry],
    participating_doc_ids: frozenset[str],
) -> tuple[SourceCatalogEntry, ...]:
    """Apply query-time participation_state projection onto catalog entries."""

    return tuple(
        replace(
            entry,
            participation_state=_resolve_participation_state(
                entry=entry,
                participating_doc_ids=participating_doc_ids,
            ),
        )
        for entry in entries
    )


def load_projected_sources(
    participating_doc_ids: frozenset[str],
    *,
    catalog_service: CatalogService | None = None,
) -> tuple[SourceCatalogEntry, ...]:
    """Load catalog entries and project participation_state for the current answer."""

    try:
        if catalog_service is None:
            from app.services.catalog_service import CatalogService

            catalog_service = CatalogService()
        service = catalog_service
        result = service.list_sources()
    except Exception:
        return ()
    return project_source_participation(result.entries, participating_doc_ids)


def _resolve_participation_state(
    *,
    entry: SourceCatalogEntry,
    participating_doc_ids: frozenset[str],
) -> SourceParticipationState | None:
    if entry.doc_id in participating_doc_ids:
        return SourceParticipationState.PARTICIPATING
    if entry.participation_state is not None:
        return entry.participation_state

    ingest_status = (entry.state.ingest_status or "").strip().lower() if entry.state is not None else ""
    if ingest_status in {"excluded"}:
        return SourceParticipationState.EXCLUDED
    if ingest_status in {"uploaded", "uploading", "pending"}:
        return SourceParticipationState.UPLOADED
    if entry.chunk_count > 0 or ingest_status in {"ready", "indexed", "completed"}:
        return SourceParticipationState.INDEXED
    return None
