"""Shared helpers for grounded retrieval, citation, evidence, and support status."""

from __future__ import annotations

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


def build_citation(hit: RetrievedChunk) -> CitationRecord:
    """Build a traceable citation record from a retrieved chunk."""

    text = hit.citation_text().strip().replace("\n", " ")
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
    )


def build_evidence(hit: RetrievedChunk) -> EvidenceObject:
    """Build a machine-consumable evidence object from one retrieved chunk."""

    text = hit.citation_text().strip().replace("\n", " ")
    score = hit.rerank_score if hit.rerank_score is not None else hit.distance
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
