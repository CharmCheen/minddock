"""Shared helpers for grounded retrieval, citation, evidence, and support status."""

from __future__ import annotations

from dataclasses import dataclass
import re

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
OUT_OF_SCOPE_ANSWER = "This question is not answerable from the current knowledge base evidence."

_OUT_OF_SCOPE_PATTERNS = (
    "what model are you",
    "which model are you",
    "who are you",
    "what are you",
    "what can you do",
    "your capabilities",
    "introduce yourself",
    "are you chatgpt",
    "你是什么模型",
    "你是什麼模型",
    "你是谁",
    "你是誰",
    "你是什么",
    "你是什麼",
    "你能做什么",
    "你能做什麼",
    "你可以做什么",
    "你可以做什麼",
    "你的能力",
    "你叫什么",
    "你叫什麼",
    "介绍一下你自己",
    "自我介绍",
)
_QUERY_STOPWORDS = {
    "about",
    "are",
    "can",
    "could",
    "does",
    "for",
    "from",
    "how",
    "into",
    "the",
    "their",
    "there",
    "this",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "with",
    "you",
    "your",
}


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


def is_out_of_scope_knowledge_query(query: str) -> bool:
    """Return true for obvious assistant/system meta questions, not KB questions."""

    normalized = _normalize_query(query)
    compact = normalized.replace(" ", "")
    return any(pattern in normalized or pattern.replace(" ", "") in compact for pattern in _OUT_OF_SCOPE_PATTERNS)


def evidence_matches_query(query: str, hits: list[RetrievedChunk]) -> bool:
    """Conservative lexical sanity check to prevent unrelated hits becoming supported evidence."""

    query_tokens = _query_tokens(query)
    if len(query_tokens) < 2:
        return True
    evidence_parts: list[str] = []
    for hit in hits:
        evidence_parts.extend(
            part
            for part in (
                hit.prompt_text(),
                hit.title,
                hit.section,
                hit.source,
                hit.ref,
            )
            if part
        )
    evidence_text = " ".join(evidence_parts).lower()
    evidence_tokens: set[str] = set()
    for token in re.findall(r"[a-z0-9]+", evidence_text):
        evidence_tokens.update(_token_variants(token))
    return bool(query_tokens & evidence_tokens)


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


def _normalize_query(query: str) -> str:
    return " ".join(query.lower().strip().split())


def _query_tokens(query: str) -> set[str]:
    tokens: set[str] = set()
    for token in re.findall(r"[a-z0-9]+", query.lower()):
        if len(token) < 3 or token in _QUERY_STOPWORDS:
            continue
        tokens.update(_token_variants(token))
    return tokens


def _token_variants(token: str) -> set[str]:
    variants = {token}
    if len(token) > 4 and token.endswith("es"):
        variants.add(token[:-2])
    if len(token) > 3 and token.endswith("s"):
        variants.add(token[:-1])
    if len(token) > 4 and token.endswith("ed"):
        variants.add(token[:-1])
        variants.add(token[:-2])
    if len(token) > 5 and token.endswith("ing"):
        variants.add(token[:-3])
    return variants
