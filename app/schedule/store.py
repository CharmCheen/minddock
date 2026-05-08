"""Thread-safe JSON-backed schedule candidate store.

File layout:
    data/
        schedule_candidates.json   <- one JSON object with "candidates" list

This store is NOT used for retrieval — only for candidate management.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.schedule.models import ScheduleCandidate

logger = logging.getLogger(__name__)

_DEFAULT_FILE = Path("data/schedule_candidates.json")

_lock = threading.Lock()


class ScheduleCandidateStoreError(Exception):
    """Raised when the store cannot recover from corruption."""


class ScheduleCandidateStore:
    """Thread-safe JSON-backed persistence for schedule candidates.

    Uses atomic write (write to .tmp then os.replace) to prevent corruption.
    """

    def __init__(self, file_path: Path | None = None) -> None:
        self._file_path = file_path or _DEFAULT_FILE

    def read_all(self) -> list[ScheduleCandidate]:
        with _lock:
            return self._read_unlocked()

    def write_all(self, candidates: list[ScheduleCandidate]) -> None:
        with _lock:
            self._write_unlocked(candidates)

    def add(self, candidate: ScheduleCandidate) -> bool:
        """Add a candidate if dedup_key does not already exist.

        Returns True if added, False if duplicate.
        """
        with _lock:
            candidates = self._read_unlocked()
            existing_keys = {c.dedup_key for c in candidates}
            if candidate.dedup_key in existing_keys:
                return False
            candidates.append(candidate)
            self._write_unlocked(candidates)
            return True

    def add_batch(self, new_candidates: list[ScheduleCandidate]) -> int:
        """Add multiple candidates, skipping duplicates.

        Returns the number of candidates actually added.
        """
        with _lock:
            candidates = self._read_unlocked()
            existing_keys = {c.dedup_key for c in candidates}
            added = 0
            for candidate in new_candidates:
                if candidate.dedup_key in existing_keys:
                    continue
                candidates.append(candidate)
                existing_keys.add(candidate.dedup_key)
                added += 1
            if added > 0:
                self._write_unlocked(candidates)
            return added

    def update_status(self, candidate_id: str, new_status: str) -> ScheduleCandidate | None:
        """Update candidate status. Returns updated candidate or None if not found.

        Does NOT overwrite confirmed/dismissed with pending.
        """
        with _lock:
            candidates = self._read_unlocked()
            for i, c in enumerate(candidates):
                if c.id == candidate_id:
                    # Guard: don't downgrade confirmed/dismissed to pending
                    if c.status in ("confirmed", "dismissed") and new_status == "pending":
                        return c
                    updated = ScheduleCandidate(
                        id=c.id,
                        title=c.title,
                        start_date=c.start_date,
                        start_time=c.start_time,
                        end_date=c.end_date,
                        end_time=c.end_time,
                        date_text=c.date_text,
                        location=c.location,
                        description=c.description,
                        source_id=c.source_id,
                        doc_id=c.doc_id,
                        chunk_id=c.chunk_id,
                        source=c.source,
                        evidence_text=c.evidence_text,
                        confidence=c.confidence,
                        status=new_status,
                        dedup_key=c.dedup_key,
                        created_at=c.created_at,
                        updated_at=_utc_now_iso(),
                    )
                    candidates[i] = updated
                    self._write_unlocked(candidates)
                    return updated
            return None

    def get_by_id(self, candidate_id: str) -> ScheduleCandidate | None:
        with _lock:
            for c in self._read_unlocked():
                if c.id == candidate_id:
                    return c
            return None

    def list_by_status(self, status: str | None = None) -> list[ScheduleCandidate]:
        with _lock:
            candidates = self._read_unlocked()
            if status is None:
                return list(candidates)
            return [c for c in candidates if c.status == status]

    def get_existing_dedup_keys(self) -> set[str]:
        """Return all existing dedup keys (for scan dedup)."""
        with _lock:
            return {c.dedup_key for c in self._read_unlocked()}

    def get_existing_dedup_keys_with_status(self) -> dict[str, str]:
        """Return {dedup_key: status} for all existing candidates."""
        with _lock:
            return {c.dedup_key: c.status for c in self._read_unlocked()}

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _read_unlocked(self) -> list[ScheduleCandidate]:
        if not self._file_path.exists():
            return []
        try:
            raw_text = self._file_path.read_text(encoding="utf-8")
            data = json.loads(raw_text)
        except json.JSONDecodeError:
            # Corrupted JSON — back up and reinitialize
            logger.warning("Corrupted JSON in %s, backing up as .corrupt", self._file_path)
            corrupt_path = self._file_path.with_suffix(".corrupt")
            try:
                shutil.copy2(self._file_path, corrupt_path)
            except OSError:
                pass
            return []
        except OSError:
            return []

        if not isinstance(data, dict):
            logger.warning("Unexpected JSON root type in %s, resetting", self._file_path)
            return []
        raw_list = data.get("candidates")
        if not isinstance(raw_list, list):
            logger.warning("Missing 'candidates' list in %s, resetting", self._file_path)
            return []
        return [ScheduleCandidate.from_dict(item) for item in raw_list if isinstance(item, dict)]

    def _write_unlocked(self, candidates: list[ScheduleCandidate]) -> None:
        self._file_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"candidates": [c.to_dict() for c in candidates]}
        tmp_path = self._file_path.with_suffix(".tmp")
        tmp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        # Atomic replace
        os.replace(str(tmp_path), str(self._file_path))


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
