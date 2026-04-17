"""Shared helpers for grounded retrieval, citation, evidence, and support status."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.rag.retrieval_models import (
    CitationRecord,
    ContextBlock,
    EvidenceObject,
    GroundedSelectionResult,
    RefusalReason,
    RetrievedChunk,
    SupportStatus,
)

SNIPPET_LIMIT = 120
MAX_EVIDENCE_DISTANCE = 1.5
PARTIAL_SUPPORT_DISTANCE = 1.0


@dataclass(frozen=True)
class GroundingAssessment:
    """Stable support assessment used by chat and summarize services."""

    support_status: SupportStatus
    refusal_reason: RefusalReason | None = None


def select_grounded_hits(hits: list[RetrievedChunk]) -> GroundedSelectionResult:
    """Filter retrieved hits down to evidence strong enough for generation."""

    grounded_hits = [
        hit
        for hit in hits
        if hit.distance is None or float(hit.distance) < MAX_EVIDENCE_DISTANCE
    ]
    return GroundedSelectionResult(hits=grounded_hits)


def build_context(hits: list[RetrievedChunk]) -> ContextBlock:
    """Assemble a prompt-ready context block from retrieved chunks."""

    return ContextBlock(chunks=hits)


def format_evidence_block(context: ContextBlock) -> str:
    """Render evidence items into a prompt-friendly text block."""

    return context.to_text()


def _extract_highlighted_sentence(
    chunk_text: str, query: str | None
) -> tuple[str | None, int | None, int | None]:
    """Extract the most query-relevant sentence from chunk text and its character offsets.

    Strategy:
    1. Split chunk_text into sentences using sentence-ending punctuation.
    2. Score each sentence by query term coverage (case-insensitive).
    3. Return the best match as (sentence, start_offset, end_offset).

    If query is None or no sentence beats the minimum threshold, fall back to
    the first sentence of the chunk or the full chunk text as last resort.

    All returned offsets are relative to chunk_text.

    Returns:
        (highlighted_sentence, position_start, position_end) or (None, None, None)
    """
    if not chunk_text or not chunk_text.strip():
        return None, None, None

    # Split into sentences — handles both English (.,!,?) and Chinese (。,！,？) delimiters.
    # We split on: . ! ? 。 ! ？ at sentence boundary, consuming the delimiter.
    sentence_pattern = re.compile(
        r"(?<=[.!?。！？])\s+"
    )
    raw_sentences = sentence_pattern.split(chunk_text)
    sentences: list[tuple[str, int, int]] = []

    cursor = 0
    for raw in raw_sentences:
        if not raw.strip():
            cursor += len(raw)
            continue
        start = chunk_text.index(raw, cursor)
        end = start + len(raw)
        sentences.append((raw.strip(), start, end))
        cursor = end

    if not sentences:
        # No sentence boundaries found — treat the whole text as one sentence
        sentences = [(chunk_text.strip(), 0, len(chunk_text))]

    if query is None:
        # No query provided — return first sentence as anchor
        s, start, end = sentences[0]
        return s, start, end

    # Score each sentence by query term overlap
    query_terms = set(query.lower().split())
    if not query_terms:
        s, start, end = sentences[0]
        return s, start, end

    best_sentence: str | None = None
    best_start: int | None = None
    best_end: int | None = None
    best_score = 0.0

    for sent_text, start, end in sentences:
        sent_lower = sent_text.lower()
        # Count how many query terms appear in this sentence
        score = sum(1 for term in query_terms if term in sent_lower)
        # Normalize by sentence length to avoid bias toward long sentences
        normalized = score / max(len(sent_text), 1)
        if normalized > best_score:
            best_score = normalized
            best_sentence = sent_text
            best_start = start
            best_end = end

    # Require at least one term match to consider it "highlighted"
    if best_score > 0 and best_sentence is not None:
        return best_sentence, best_start, best_end

    # Fallback: return first sentence even with no match
    s, start, end = sentences[0]
    return s, start, end


def build_citation(hit: RetrievedChunk, query: str | None = None) -> CitationRecord:
    """Build a traceable citation record from a retrieved chunk.

    Args:
        hit: The retrieved chunk containing text and metadata.
        query: Optional query string. When provided, used to extract a
            query-relevant highlighted_sentence with character offsets.
            Offsets are relative to hit.text (the chunk content).
    """

    text = hit.citation_text().strip().replace("\n", " ")
    # block_id and section_path come from ingest-time metadata (pre-computed)
    block_id = _metadata_text(hit, "block_id")
    section_path = _metadata_text(hit, "section_path")
    # highlighted_sentence and offsets are always computed from chunk text
    # so they reflect the current query context accurately
    highlighted_sentence, position_start, position_end = _extract_highlighted_sentence(
        hit.text, query
    )

    return CitationRecord(
        doc_id=hit.doc_id,
        chunk_id=hit.chunk_id,
        source=hit.source,
        snippet=text[:SNIPPET_LIMIT],
        page=hit.page,
        anchor=(hit.anchor or None),
        title=hit.title or None,
        section=hit.section or None,
        location=hit.location or None,
        ref=hit.ref or hit.title or hit.source or None,
        block_id=block_id,
        highlighted_sentence=highlighted_sentence,
        position_start=position_start,
        position_end=position_end,
        section_path=section_path,
    )


def build_evidence(hit: RetrievedChunk, query: str | None = None) -> EvidenceObject:
    """Build a machine-consumable evidence object from one retrieved chunk.

    Args:
        hit: The retrieved chunk containing text and metadata.
        query: Optional query string. When provided, used to extract a
            query-relevant highlighted_sentence with character offsets.
            Offsets are relative to hit.text (the chunk content).
    """

    text = hit.citation_text().strip().replace("\n", " ")
    score = hit.rerank_score if hit.rerank_score is not None else hit.distance
    # block_id comes from ingest-time metadata (pre-computed)
    block_id = _metadata_text(hit, "block_id")
    # highlighted_sentence and offsets are always computed from chunk text
    highlighted_sentence, position_start, position_end = _extract_highlighted_sentence(
        hit.text, query
    )

    return EvidenceObject(
        doc_id=hit.doc_id,
        chunk_id=hit.chunk_id,
        source=hit.source,
        page=hit.page,
        anchor=hit.anchor or None,
        snippet=text[:SNIPPET_LIMIT],
        score=score,
        source_version=_metadata_text(hit, "source_version"),
        content_hash=_metadata_text(hit, "content_hash") or _metadata_text(hit, "hash"),
        block_id=block_id,
        highlighted_sentence=highlighted_sentence,
        position_start=position_start,
        position_end=position_end,
    )


def assess_grounding(
    *,
    retrieved_hits: list[RetrievedChunk],
    evidence: list[EvidenceObject],
) -> GroundingAssessment:
    """Classify support strength using a small, stable, and testable heuristic."""

    if not retrieved_hits:
        return GroundingAssessment(
            support_status=SupportStatus.INSUFFICIENT_EVIDENCE,
            refusal_reason=RefusalReason.NO_RELEVANT_EVIDENCE,
        )

    if not evidence:
        if not any(hit.distance is None or float(hit.distance) < MAX_EVIDENCE_DISTANCE for hit in retrieved_hits):
            return GroundingAssessment(
                support_status=SupportStatus.INSUFFICIENT_EVIDENCE,
                refusal_reason=RefusalReason.NO_RELEVANT_EVIDENCE,
            )
        return GroundingAssessment(
            support_status=SupportStatus.INSUFFICIENT_EVIDENCE,
            refusal_reason=RefusalReason.INSUFFICIENT_CONTEXT,
        )

    strong_evidence = [
        item
        for item in evidence
        if item.score is None or float(item.score) <= PARTIAL_SUPPORT_DISTANCE
    ]
    if strong_evidence:
        return GroundingAssessment(support_status=SupportStatus.SUPPORTED)

    return GroundingAssessment(support_status=SupportStatus.PARTIALLY_SUPPORTED)


def _metadata_text(hit: RetrievedChunk, key: str) -> str | None:
    value = hit.extra_metadata.get(key)
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _metadata_int(hit: RetrievedChunk, key: str) -> int | None:
    value = hit.extra_metadata.get(key)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
