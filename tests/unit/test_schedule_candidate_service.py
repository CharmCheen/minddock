"""Unit tests for schedule candidate service."""

import pytest
from types import SimpleNamespace

from app.schedule.models import ScheduleCandidate
from app.schedule.store import ScheduleCandidateStore
from app.services.schedule_candidate_service import ScheduleCandidateService


class FakeVectorstore:
    """Minimal vectorstore mock that uses the public get_document_chunks API."""

    def __init__(self, chunks: list[dict] | None = None, sources: list[dict] | None = None):
        self._chunks = chunks or []
        self._sources = sources or [
            {"doc_id": "doc-1", "source": "notes.md"},
        ]

    def list_source_details(self):
        return [
            SimpleNamespace(
                entry=SimpleNamespace(doc_id=s["doc_id"], source=s["source"]),
            )
            for s in self._sources
        ]

    def get_document_chunks(self, doc_id: str, **kwargs):
        rows = [c for c in self._chunks if c.get("doc_id") == doc_id]
        return [
            {
                "chunk_id": r["chunk_id"],
                "doc_id": r["doc_id"],
                "source": r.get("source", ""),
                "text": r.get("text", ""),
            }
            for r in rows
        ]


@pytest.fixture
def tmp_store(tmp_path):
    return ScheduleCandidateStore(file_path=tmp_path / "candidates.json")


@pytest.fixture
def fake_vs():
    return FakeVectorstore(
        chunks=[
            {
                "doc_id": "doc-1",
                "chunk_id": "chunk-1",
                "source": "notes.md",
                "text": "2026-05-20 14:00 答辩",
            },
            {
                "doc_id": "doc-1",
                "chunk_id": "chunk-2",
                "source": "notes.md",
                "text": "普通文本没有日期",
            },
        ],
        sources=[
            {"doc_id": "doc-1", "source": "notes.md"},
        ],
    )


@pytest.fixture
def service(tmp_store, fake_vs):
    return ScheduleCandidateService(store=tmp_store, vectorstore=fake_vs)


class TestScheduleCandidateService:
    def test_scan_generates_candidates(self, service, tmp_store):
        result = service.scan()
        assert result["chunks_scanned"] == 2
        assert result["candidates_extracted"] >= 1
        assert result["candidates_added"] >= 1
        candidates = tmp_store.read_all()
        assert len(candidates) >= 1
        assert candidates[0].status == "pending"

    def test_scan_no_duplicate_on_second_run(self, service, tmp_store):
        service.scan()
        count_after_first = len(tmp_store.read_all())
        result2 = service.scan()
        assert result2["candidates_added"] == 0
        assert len(tmp_store.read_all()) == count_after_first

    def test_scan_with_doc_id(self, service, tmp_store):
        result = service.scan(doc_id="doc-1")
        assert result["chunks_scanned"] == 2

    def test_scan_with_source_filter(self, tmp_store):
        """Source filter should only scan matching documents."""
        vs = FakeVectorstore(
            chunks=[
                {"doc_id": "d1", "chunk_id": "c1", "source": "a.md", "text": "2026-05-20 答辩"},
                {"doc_id": "d2", "chunk_id": "c2", "source": "b.md", "text": "2026-06-01 会议"},
            ],
            sources=[
                {"doc_id": "d1", "source": "a.md"},
                {"doc_id": "d2", "source": "b.md"},
            ],
        )
        svc = ScheduleCandidateService(store=tmp_store, vectorstore=vs)
        result = svc.scan(source="a.md")
        assert result["chunks_scanned"] == 1
        assert result["candidates_added"] >= 1
        # Only the a.md candidate should be in the store
        candidates = tmp_store.read_all()
        assert all(c.source == "a.md" for c in candidates)

    def test_scan_without_source_scans_all(self, tmp_store):
        vs = FakeVectorstore(
            chunks=[
                {"doc_id": "d1", "chunk_id": "c1", "source": "a.md", "text": "2026-05-20 答辩"},
                {"doc_id": "d2", "chunk_id": "c2", "source": "b.md", "text": "2026-06-01 会议"},
            ],
            sources=[
                {"doc_id": "d1", "source": "a.md"},
                {"doc_id": "d2", "source": "b.md"},
            ],
        )
        svc = ScheduleCandidateService(store=tmp_store, vectorstore=vs)
        result = svc.scan()
        assert result["chunks_scanned"] == 2

    def test_list_candidates(self, service, tmp_store):
        service.scan()
        candidates = service.list_candidates()
        assert len(candidates) >= 1

    def test_list_candidates_by_status(self, service, tmp_store):
        service.scan()
        pending = service.list_candidates(status="pending")
        assert len(pending) >= 1
        confirmed = service.list_candidates(status="confirmed")
        assert len(confirmed) == 0

    def test_confirm_candidate(self, service, tmp_store):
        service.scan()
        candidates = tmp_store.read_all()
        assert len(candidates) >= 1
        candidate_id = candidates[0].id
        result = service.confirm(candidate_id)
        assert result is not None
        assert result.status == "confirmed"

    def test_dismiss_candidate(self, service, tmp_store):
        service.scan()
        candidates = tmp_store.read_all()
        candidate_id = candidates[0].id
        result = service.dismiss(candidate_id)
        assert result is not None
        assert result.status == "dismissed"

    def test_confirm_not_found(self, service):
        result = service.confirm("nonexistent")
        assert result is None

    def test_dismiss_not_found(self, service):
        result = service.dismiss("nonexistent")
        assert result is None

    def test_candidate_has_required_fields(self, service, tmp_store):
        service.scan()
        candidates = tmp_store.read_all()
        c = candidates[0]
        assert c.id
        assert c.title
        assert c.doc_id == "doc-1"
        assert c.chunk_id
        assert c.source == "notes.md"
        assert c.evidence_text
        assert c.dedup_key
        assert c.confidence > 0

    def test_scan_does_not_overwrite_confirmed(self, service, tmp_store):
        service.scan()
        candidates = tmp_store.read_all()
        c = candidates[0]
        service.confirm(c.id)
        result = service.scan()
        confirmed = [x for x in tmp_store.read_all() if x.status == "confirmed"]
        assert len(confirmed) == 1
        assert confirmed[0].id == c.id

    def test_empty_vectorstore(self, tmp_store):
        empty_vs = FakeVectorstore(chunks=[], sources=[])
        svc = ScheduleCandidateService(store=tmp_store, vectorstore=empty_vs)
        result = svc.scan()
        assert result["chunks_scanned"] == 0
        assert result["candidates_added"] == 0
