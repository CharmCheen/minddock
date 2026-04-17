"""Unit tests for query-time source participation projection."""

from app.rag.retrieval_models import CitationRecord
from app.rag.source_models import SourceCatalogEntry, SourceParticipationState, SourceState
from app.services.participation import extract_participating_doc_ids, project_source_participation


def _entry(doc_id: str) -> SourceCatalogEntry:
    return SourceCatalogEntry(
        doc_id=doc_id,
        source=f"kb/{doc_id}.md",
        source_type="file",
        title=doc_id,
        chunk_count=1,
        state=SourceState(
            doc_id=doc_id,
            source=f"kb/{doc_id}.md",
            chunk_count=1,
            ingest_status="ready",
        ),
    )


def test_project_source_participation_marks_only_cited_documents() -> None:
    projected = project_source_participation(
        (_entry("d1"), _entry("d2")),
        frozenset({"d1"}),
    )

    assert projected[0].participation_state == SourceParticipationState.PARTICIPATING
    assert projected[1].participation_state == SourceParticipationState.INDEXED


def test_project_source_participation_is_stable_without_citations() -> None:
    projected = project_source_participation(
        (_entry("d1"), _entry("d2")),
        frozenset(),
    )

    assert [entry.participation_state for entry in projected] == [
        SourceParticipationState.INDEXED,
        SourceParticipationState.INDEXED,
    ]


def test_project_source_participation_refreshes_between_answers() -> None:
    entries = (_entry("d1"), _entry("d2"))

    first_round = project_source_participation(entries, frozenset({"d1"}))
    second_round = project_source_participation(entries, frozenset({"d2"}))

    assert first_round[0].participation_state == SourceParticipationState.PARTICIPATING
    assert first_round[1].participation_state == SourceParticipationState.INDEXED
    assert second_round[0].participation_state == SourceParticipationState.INDEXED
    assert second_round[1].participation_state == SourceParticipationState.PARTICIPATING


def test_extract_participating_doc_ids_deduplicates_citations() -> None:
    doc_ids = extract_participating_doc_ids(
        (
            CitationRecord(doc_id="d1", chunk_id="c1", source="kb/a.md", snippet="alpha"),
            CitationRecord(doc_id="d1", chunk_id="c2", source="kb/a.md", snippet="beta"),
            CitationRecord(doc_id="d2", chunk_id="c3", source="kb/b.md", snippet="gamma"),
        )
    )

    assert doc_ids == frozenset({"d1", "d2"})
