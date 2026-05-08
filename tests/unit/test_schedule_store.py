"""Unit tests for schedule candidate JSON store."""

import json
import pytest
from pathlib import Path

from app.schedule.models import ScheduleCandidate
from app.schedule.store import ScheduleCandidateStore


@pytest.fixture
def tmp_store(tmp_path):
    """Create a store using a temporary file."""
    file_path = tmp_path / "schedule_candidates.json"
    return ScheduleCandidateStore(file_path=file_path)


@pytest.fixture
def sample_candidate():
    return ScheduleCandidate(
        id="test-id-001",
        title="答辩",
        start_date="2026-05-20",
        start_time="14:00",
        end_date=None,
        end_time=None,
        date_text="2026-05-20",
        location=None,
        description="2026-05-20 14:00 答辩",
        source_id="doc-1",
        doc_id="doc-1",
        chunk_id="chunk-1",
        source="test.md",
        evidence_text="2026-05-20 14:00 答辩",
        confidence=0.9,
        status="pending",
        dedup_key="dedup-key-001",
    )


class TestScheduleCandidateStore:
    def test_read_empty(self, tmp_store):
        assert tmp_store.read_all() == []

    def test_write_and_read(self, tmp_store, sample_candidate):
        tmp_store.write_all([sample_candidate])
        loaded = tmp_store.read_all()
        assert len(loaded) == 1
        assert loaded[0].id == sample_candidate.id
        assert loaded[0].title == sample_candidate.title

    def test_add_new(self, tmp_store, sample_candidate):
        assert tmp_store.add(sample_candidate) is True
        assert len(tmp_store.read_all()) == 1

    def test_add_duplicate(self, tmp_store, sample_candidate):
        tmp_store.add(sample_candidate)
        assert tmp_store.add(sample_candidate) is False
        assert len(tmp_store.read_all()) == 1

    def test_add_batch(self, tmp_store):
        candidates = [
            ScheduleCandidate(
                id=f"id-{i}",
                title=f"title-{i}",
                start_date="2026-05-20",
                confidence=0.7,
                status="pending",
                dedup_key=f"key-{i}",
            )
            for i in range(3)
        ]
        added = tmp_store.add_batch(candidates)
        assert added == 3
        assert len(tmp_store.read_all()) == 3

    def test_add_batch_skips_duplicates(self, tmp_store, sample_candidate):
        tmp_store.add(sample_candidate)
        added = tmp_store.add_batch([sample_candidate])
        assert added == 0
        assert len(tmp_store.read_all()) == 1

    def test_update_status_confirm(self, tmp_store, sample_candidate):
        tmp_store.add(sample_candidate)
        updated = tmp_store.update_status(sample_candidate.id, "confirmed")
        assert updated is not None
        assert updated.status == "confirmed"

    def test_update_status_dismiss(self, tmp_store, sample_candidate):
        tmp_store.add(sample_candidate)
        updated = tmp_store.update_status(sample_candidate.id, "dismissed")
        assert updated is not None
        assert updated.status == "dismissed"

    def test_update_status_not_found(self, tmp_store):
        result = tmp_store.update_status("nonexistent", "confirmed")
        assert result is None

    def test_no_overwrite_confirmed(self, tmp_store, sample_candidate):
        tmp_store.add(sample_candidate)
        tmp_store.update_status(sample_candidate.id, "confirmed")
        updated = tmp_store.update_status(sample_candidate.id, "pending")
        assert updated is not None
        assert updated.status == "confirmed"

    def test_no_overwrite_dismissed(self, tmp_store, sample_candidate):
        tmp_store.add(sample_candidate)
        tmp_store.update_status(sample_candidate.id, "dismissed")
        updated = tmp_store.update_status(sample_candidate.id, "pending")
        assert updated is not None
        assert updated.status == "dismissed"

    def test_get_by_id(self, tmp_store, sample_candidate):
        tmp_store.add(sample_candidate)
        found = tmp_store.get_by_id(sample_candidate.id)
        assert found is not None
        assert found.id == sample_candidate.id

    def test_get_by_id_not_found(self, tmp_store):
        assert tmp_store.get_by_id("nonexistent") is None

    def test_list_by_status(self, tmp_store):
        c1 = ScheduleCandidate(id="a", title="A", status="pending", dedup_key="k1")
        c2 = ScheduleCandidate(id="b", title="B", status="confirmed", dedup_key="k2")
        c3 = ScheduleCandidate(id="c", title="C", status="pending", dedup_key="k3")
        tmp_store.write_all([c1, c2, c3])

        pending = tmp_store.list_by_status("pending")
        assert len(pending) == 2
        confirmed = tmp_store.list_by_status("confirmed")
        assert len(confirmed) == 1
        all_items = tmp_store.list_by_status()
        assert len(all_items) == 3

    def test_get_existing_dedup_keys(self, tmp_store, sample_candidate):
        tmp_store.add(sample_candidate)
        keys = tmp_store.get_existing_dedup_keys()
        assert sample_candidate.dedup_key in keys

    def test_get_existing_dedup_keys_with_status(self, tmp_store, sample_candidate):
        tmp_store.add(sample_candidate)
        keys = tmp_store.get_existing_dedup_keys_with_status()
        assert keys[sample_candidate.dedup_key] == "pending"

    def test_corrupted_json_returns_empty_and_creates_backup(self, tmp_path):
        file_path = tmp_path / "bad.json"
        file_path.write_text("not valid json{{{", encoding="utf-8")
        store = ScheduleCandidateStore(file_path=file_path)
        result = store.read_all()
        assert result == []
        # Should have created a .corrupt backup
        corrupt_path = file_path.with_suffix(".corrupt")
        assert corrupt_path.exists()
        assert corrupt_path.read_text(encoding="utf-8") == "not valid json{{{"

    def test_missing_file_returns_empty(self, tmp_path):
        store = ScheduleCandidateStore(file_path=tmp_path / "nonexistent.json")
        assert store.read_all() == []

    def test_atomic_write_no_tmp残留(self, tmp_store, sample_candidate):
        """After write, no .tmp file should remain."""
        tmp_store.add(sample_candidate)
        tmp_path = tmp_store._file_path.parent
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert len(tmp_files) == 0

    def test_write_read_consistency(self, tmp_store):
        """Write a batch, read back, verify all fields survive roundtrip."""
        candidates = [
            ScheduleCandidate(
                id=f"id-{i}",
                title=f"title-{i}",
                start_date="2026-05-20",
                start_time="14:00",
                end_time="15:00",
                date_text="2026-05-20",
                doc_id="doc-1",
                chunk_id=f"chunk-{i}",
                source="test.md",
                evidence_text=f"evidence {i}",
                confidence=0.7,
                status="pending",
                dedup_key=f"key-{i}",
            )
            for i in range(5)
        ]
        tmp_store.write_all(candidates)
        loaded = tmp_store.read_all()
        assert len(loaded) == 5
        for i, c in enumerate(loaded):
            assert c.id == f"id-{i}"
            assert c.title == f"title-{i}"
            assert c.start_date == "2026-05-20"
            assert c.start_time == "14:00"
            assert c.end_time == "15:00"
            assert c.evidence_text == f"evidence {i}"
