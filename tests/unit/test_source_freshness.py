"""Unit tests for evidence freshness resolution."""

from app.rag.retrieval_models import EvidenceFreshness, EvidenceObject, GroundedAnswer
from app.rag.source_models import SourceCatalogEntry, SourceDetail, SourceState
from app.services.source_freshness import refresh_evidence_freshness, refresh_grounded_answer_freshness


class FakeCollection:
    def __init__(self, *, details, chunk_ids) -> None:
        self._details = details
        self._chunk_ids = chunk_ids

    def list_source_details(self, query=None):
        return list(self._details)

    def list_document_chunk_ids(self, doc_id: str):
        return list(self._chunk_ids.get(doc_id, ()))


def _detail(*, version: str = "v1", chunk_id: str = "c1") -> SourceDetail:
    return SourceDetail(
        entry=SourceCatalogEntry(
            doc_id="d1",
            source="kb/doc.md",
            source_type="file",
            title="doc",
            chunk_count=1,
            state=SourceState(
                doc_id="d1",
                source="kb/doc.md",
                current_version=version,
                content_hash=version,
                last_ingested_at="2026-04-05T10:00:00+00:00",
                chunk_count=1,
                ingest_status="ready",
            ),
        ),
        representative_metadata={"content_hash": version},
    )


def test_evidence_defaults_to_fresh_when_version_matches() -> None:
    evidence = EvidenceObject(
        doc_id="d1",
        chunk_id="c1",
        source="kb/doc.md",
        snippet="proof",
        source_version="v1",
        content_hash="v1",
    )

    refreshed = refresh_evidence_freshness(
        evidence,
        collection=FakeCollection(details=[_detail(version="v1")], chunk_ids={"d1": {"c1"}}),
    )

    assert refreshed.freshness == EvidenceFreshness.FRESH


def test_old_evidence_becomes_stale_possible_after_source_update() -> None:
    grounded = GroundedAnswer(
        answer="answer",
        evidence=(
            EvidenceObject(
                doc_id="d1",
                chunk_id="c1",
                source="kb/doc.md",
                snippet="proof",
                source_version="v1",
                content_hash="v1",
            ),
        ),
    )

    refreshed = refresh_grounded_answer_freshness(
        grounded,
        collection=FakeCollection(details=[_detail(version="v2")], chunk_ids={"d1": {"c1"}}),
    )

    assert refreshed.evidence[0].freshness == EvidenceFreshness.STALE_POSSIBLE


def test_old_evidence_becomes_invalidated_when_source_or_chunk_disappears() -> None:
    evidence = EvidenceObject(
        doc_id="d1",
        chunk_id="c1",
        source="kb/doc.md",
        snippet="proof",
        source_version="v1",
    )

    missing_source = refresh_evidence_freshness(
        evidence,
        collection=FakeCollection(details=[], chunk_ids={}),
    )
    missing_chunk = refresh_evidence_freshness(
        evidence,
        collection=FakeCollection(details=[_detail(version="v1")], chunk_ids={"d1": {"c2"}}),
    )

    assert missing_source.freshness == EvidenceFreshness.INVALIDATED
    assert missing_chunk.freshness == EvidenceFreshness.INVALIDATED
