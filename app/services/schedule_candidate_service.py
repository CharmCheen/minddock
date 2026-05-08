"""Schedule candidate service — scan, list, confirm, dismiss.

This service reads chunks via the existing vectorstore public API
and applies rule-based extraction. It does NOT modify the
vectorstore, RAG pipeline, or ingestion flow.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from app.schedule.extractor import extract_candidates_from_text
from app.schedule.models import ScheduleCandidate
from app.schedule.store import ScheduleCandidateStore

logger = logging.getLogger(__name__)

_VALID_STATUSES = frozenset({"pending", "confirmed", "dismissed"})


class ScheduleCandidateService:
    """Orchestrate schedule candidate scan and lifecycle management."""

    def __init__(
        self,
        *,
        store: ScheduleCandidateStore | None = None,
        vectorstore: Any | None = None,
    ) -> None:
        self._store = store or ScheduleCandidateStore()
        self._vectorstore = vectorstore

    def scan(
        self,
        *,
        doc_id: str | None = None,
        source: str | None = None,
    ) -> dict[str, Any]:
        """Scan chunks for schedule candidates.

        If doc_id is provided, scan only that document.
        If source is provided, scan only documents matching that source.
        Otherwise scan all indexed documents.

        Returns a summary dict with added/skipped/total counts.
        """
        started = time.perf_counter()

        # Get chunks to scan
        chunk_rows = self._get_chunks(doc_id=doc_id, source=source)

        # Extract candidates from all chunks
        all_candidates: list[ScheduleCandidate] = []
        for row in chunk_rows:
            text = row.get("text", "")
            row_doc_id = row.get("doc_id", "")
            row_chunk_id = row.get("chunk_id", "")
            row_source = row.get("source", "")
            candidates = extract_candidates_from_text(
                text,
                doc_id=row_doc_id,
                chunk_id=row_chunk_id,
                source=row_source,
            )
            all_candidates.extend(candidates)

        # Dedup against existing store
        existing = self._store.get_existing_dedup_keys_with_status()
        new_candidates: list[ScheduleCandidate] = []
        skipped_existing = 0

        for c in all_candidates:
            if c.dedup_key in existing:
                skipped_existing += 1
                continue
            new_candidates.append(c)

        # Batch add
        added = self._store.add_batch(new_candidates)

        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.info(
            "Schedule scan completed: chunks=%d extracted=%d added=%d skipped=%d elapsed_ms=%s",
            len(chunk_rows), len(all_candidates), added, skipped_existing, elapsed_ms,
        )

        return {
            "chunks_scanned": len(chunk_rows),
            "candidates_extracted": len(all_candidates),
            "candidates_added": added,
            "candidates_skipped": skipped_existing,
            "elapsed_ms": elapsed_ms,
        }

    def list_candidates(self, *, status: str | None = None) -> list[ScheduleCandidate]:
        """List candidates, optionally filtered by status."""
        return self._store.list_by_status(status=status)

    def get_candidate(self, candidate_id: str) -> ScheduleCandidate | None:
        return self._store.get_by_id(candidate_id)

    def confirm(self, candidate_id: str) -> ScheduleCandidate | None:
        return self._store.update_status(candidate_id, "confirmed")

    def dismiss(self, candidate_id: str) -> ScheduleCandidate | None:
        return self._store.update_status(candidate_id, "dismissed")

    # ------------------------------------------------------------------
    # Internal chunk access — uses only public vectorstore methods
    # ------------------------------------------------------------------

    def _get_chunks(
        self,
        *,
        doc_id: str | None = None,
        source: str | None = None,
    ) -> list[dict[str, str]]:
        """Retrieve chunks from the vectorstore using public API only.

        Returns list of dicts with keys: doc_id, chunk_id, source, text.
        """
        vs = self._vectorstore
        if vs is None:
            from app.rag.vectorstore import get_vectorstore
            vs = get_vectorstore()

        # Single doc_id — direct lookup
        if doc_id:
            return vs.get_document_chunks(doc_id)

        # Need to iterate all documents
        try:
            details = vs.list_source_details()
        except Exception:
            logger.warning("Failed to list source details for schedule scan")
            return []

        all_rows: list[dict[str, str]] = []
        for detail in details:
            entry_doc_id = detail.entry.doc_id
            entry_source = detail.entry.source

            # Apply source filter
            if source and entry_source != source:
                continue

            rows = vs.get_document_chunks(entry_doc_id)
            # Annotate source if missing
            for row in rows:
                if not row.get("source"):
                    row["source"] = entry_source
            all_rows.extend(rows)

        return all_rows
