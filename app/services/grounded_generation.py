"""Shared helpers for grounded retrieval, citation, evidence, and support status."""

from __future__ import annotations

from dataclasses import dataclass
import re
from collections.abc import Callable

from app.rag.retrieval_models import (
    CitationRecord,
    ContextBlock,
    EvidenceObject,
    EvidenceWindow,
    GroundedSelectionResult,
    RefusalReason,
    RetrievedChunk,
    SupportStatus,
)

SNIPPET_LIMIT = 120
EVIDENCE_PREVIEW_LIMIT = 220
CITATION_LABEL_SECTION_LIMIT = 48
MAX_EVIDENCE_DISTANCE = 1.5
PARTIAL_SUPPORT_DISTANCE = 1.0
OUT_OF_SCOPE_ANSWER = "This question is not answerable from the current knowledge base evidence."

HELPFUL_CHAT_INSUFFICIENT_EVIDENCE = (
    "我没有在当前知识库中找到足够直接的证据来回答这个问题，因此不能给出带引用的结论。"
    "\n\n你可以尝试："
    "\n1. 使用更接近原文的关键词重新提问；"
    "\n2. 在 Sources 中确认相关文档、音频或视频是否已经成功入库；"
    "\n3. 打开 Source Drawer 查看转录文本是否存在；"
    "\n4. 指定某个来源后重新提问。"
)
MAX_EVIDENCE_WINDOW_BLOCKS = 5
MAX_EVIDENCE_WINDOW_CHARS = 2400

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
    "a",
    "about",
    "an",
    "and",
    "are",
    "can",
    "could",
    "does",
    "do",
    "for",
    "from",
    "how",
    "i",
    "is",
    "of",
    "into",
    "to",
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
_WEAK_ALIGNMENT_TERMS = {
    "component",
    "components",
    "current",
    "design",
    "explain",
    "key",
    "latest",
    "make",
    "move",
    "moves",
    "population",
    "price",
    "prices",
    "rule",
    "rules",
    "scratch",
    "simple",
    "stock",
    "stocks",
    "system",
    "terms",
    "theory",
}
_OPEN_DOMAIN_SENSITIVE_TERMS = {
    "apple",
    "bake",
    "cake",
    "capital",
    "chess",
    "chocolate",
    "cook",
    "france",
    "knight",
    "population",
    "price",
    "prices",
    "recipe",
    "relativity",
    "stock",
    "stocks",
    "tesla",
}


@dataclass(frozen=True)
class GroundingAssessment:
    """Stable support assessment used by chat and summarize services."""

    support_status: SupportStatus
    refusal_reason: RefusalReason | None = None


@dataclass(frozen=True)
class EvidenceQueryAlignment:
    """Explainable query/evidence alignment gate result."""

    passed: bool
    reason: str
    query_terms: tuple[str, ...] = ()
    core_terms: tuple[str, ...] = ()
    overlap_terms: tuple[str, ...] = ()
    missing_core_terms: tuple[str, ...] = ()
    overlap_ratio: float = 0.0
    source_count: int = 0

    def to_trace_dict(self) -> dict[str, object]:
        return {
            "triggered": not self.passed,
            "reason": self.reason,
            "query_terms": list(self.query_terms),
            "core_terms": list(self.core_terms),
            "overlap_terms": list(self.overlap_terms),
            "missing_core_terms": list(self.missing_core_terms),
            "overlap_ratio": self.overlap_ratio,
            "source_count": self.source_count,
        }


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

    return assess_evidence_query_alignment(query, hits).passed


def assess_evidence_query_alignment(query: str, hits: list[RetrievedChunk]) -> EvidenceQueryAlignment:
    """Return an explainable conservative gate for obvious query/evidence mismatch."""

    query_terms = _query_terms(query)
    if len(query_terms) < 2:
        return EvidenceQueryAlignment(
            passed=True,
            reason="too_few_query_terms",
            query_terms=tuple(sorted(query_terms)),
            source_count=_source_count(hits),
        )

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
    evidence_terms = _expanded_terms(" ".join(evidence_parts))
    query_expanded = _expand_term_set(query_terms)
    overlap_terms = tuple(sorted(term for term in query_terms if _token_variants(term) & evidence_terms))
    overlap_ratio = round(len(overlap_terms) / max(len(query_terms), 1), 3)
    core_terms = _core_query_terms(query_terms)
    missing_core_terms = tuple(sorted(term for term in core_terms if not (_token_variants(term) & evidence_terms)))
    core_overlap_count = len(core_terms) - len(missing_core_terms)
    source_count = _source_count(hits)

    if not query_expanded & evidence_terms:
        return EvidenceQueryAlignment(
            passed=False,
            reason="no_query_evidence_overlap",
            query_terms=tuple(sorted(query_terms)),
            core_terms=tuple(sorted(core_terms)),
            overlap_terms=overlap_terms,
            missing_core_terms=missing_core_terms,
            overlap_ratio=overlap_ratio,
            source_count=source_count,
        )

    if core_terms and core_overlap_count == 0:
        return EvidenceQueryAlignment(
            passed=False,
            reason="missing_core_query_terms",
            query_terms=tuple(sorted(query_terms)),
            core_terms=tuple(sorted(core_terms)),
            overlap_terms=overlap_terms,
            missing_core_terms=missing_core_terms,
            overlap_ratio=overlap_ratio,
            source_count=source_count,
        )

    if _is_open_domain_sensitive_query(query_terms) and core_terms:
        required_core_overlap = min(2, len(core_terms))
        if core_overlap_count < required_core_overlap:
            return EvidenceQueryAlignment(
                passed=False,
                reason="missing_core_query_terms",
                query_terms=tuple(sorted(query_terms)),
                core_terms=tuple(sorted(core_terms)),
                overlap_terms=overlap_terms,
                missing_core_terms=missing_core_terms,
                overlap_ratio=overlap_ratio,
                source_count=source_count,
            )

    return EvidenceQueryAlignment(
        passed=True,
        reason="aligned",
        query_terms=tuple(sorted(query_terms)),
        core_terms=tuple(sorted(core_terms)),
        overlap_terms=overlap_terms,
        missing_core_terms=missing_core_terms,
        overlap_ratio=overlap_ratio,
        source_count=source_count,
    )


def build_context(hits: list[RetrievedChunk]) -> ContextBlock:
    """Assemble a prompt-ready context block from retrieved chunks."""

    return ContextBlock(chunks=hits)


NeighborLoader = Callable[[RetrievedChunk, int, int], list[RetrievedChunk]]


def expand_evidence_windows(
    hits: list[RetrievedChunk],
    *,
    neighbor_loader: NeighborLoader | None = None,
) -> list[RetrievedChunk]:
    """Expand retrieved child chunks into conservative answer/citation windows."""

    if not hits or neighbor_loader is None:
        return hits

    windows = [_build_window(hit, neighbor_loader) for hit in hits]
    merged_windows = _merge_overlapping_windows(windows)
    return [window.to_retrieved_chunk() for window in merged_windows]


def format_evidence_block(context: ContextBlock) -> str:
    """Render evidence items into a prompt-friendly text block."""

    return context.to_text()


def _derived_metadata(hit: RetrievedChunk) -> dict[str, object]:
    """Extract derived chunk provenance from extra_metadata."""
    meta = hit.extra_metadata
    is_derived = str(meta.get("is_derived") or "").strip().lower() == "true"
    if not is_derived:
        return {
            "is_derived": False,
            "derived_kind": None,
            "derived_from": None,
            "derived_basis": None,
            "evidence_basis": None,
            "transcript_provider": _metadata_text(hit, "transcript_provider"),
            "retrieval_basis": _metadata_text(hit, "retrieval_basis"),
        }
    return {
        "is_derived": True,
        "derived_kind": _metadata_text(hit, "derived_kind"),
        "derived_from": _metadata_text(hit, "derived_from"),
        "derived_basis": _metadata_text(hit, "derived_basis"),
        "evidence_basis": _metadata_text(hit, "evidence_basis"),
        "transcript_provider": _metadata_text(hit, "transcript_provider"),
        "retrieval_basis": _metadata_text(hit, "retrieval_basis"),
    }


def build_citation(hit: RetrievedChunk) -> CitationRecord:
    """Build a traceable citation record from a retrieved chunk."""

    text = hit.citation_text().strip().replace("\n", " ")
    window_metadata = _citation_window_metadata(hit, text=text)
    derived = _derived_metadata(hit)
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
        **window_metadata,
        **derived,
    )


def build_evidence(hit: RetrievedChunk) -> EvidenceObject:
    """Build a machine-consumable evidence object from one retrieved chunk."""

    text = hit.citation_text().strip().replace("\n", " ")
    score = hit.rerank_score if hit.rerank_score is not None else hit.distance
    window_metadata = _citation_window_metadata(hit, text=text)
    derived = _derived_metadata(hit)
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
        **window_metadata,
        **derived,
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
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _metadata_text_tuple(hit: RetrievedChunk, key: str) -> tuple[str, ...]:
    value = hit.extra_metadata.get(key)
    if value is None:
        return ()
    if isinstance(value, (list, tuple, set)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    normalized = str(value).strip()
    return (normalized,) if normalized else ()


def _citation_window_metadata(hit: RetrievedChunk, *, text: str) -> dict[str, object]:
    hit_chunk_id = _metadata_text(hit, "hit_chunk_id") or hit.chunk_id
    window_chunk_ids = _metadata_text_tuple(hit, "window_chunk_ids")
    if not window_chunk_ids and hit_chunk_id:
        window_chunk_ids = (hit_chunk_id,)
    page_start = _metadata_int(hit, "page_start") or hit.page
    page_end = _metadata_int(hit, "page_end") or hit.page
    section_title = _metadata_text(hit, "section_title") or hit.section or None
    block_types = _metadata_text_tuple(hit, "block_types")
    if not block_types:
        hit_block_type = _metadata_text(hit, "block_type")
        block_types = (hit_block_type,) if hit_block_type else ()
    evidence_window_reason = _metadata_text(hit, "evidence_window_reason")
    window_chunk_count = len(window_chunk_ids)
    hit_in_window = bool(hit_chunk_id and hit_chunk_id in window_chunk_ids)
    is_hit_only_fallback = bool(
        hit_in_window
        and window_chunk_count == 1
        and (evidence_window_reason in {None, "hit_only"} or window_chunk_ids[0] == hit_chunk_id)
    )
    is_windowed = bool(evidence_window_reason and evidence_window_reason != "hit_only" and window_chunk_count > 1)
    hit_page = _metadata_int(hit, "hit_page") or hit.page or page_start
    hit_order_in_doc = _metadata_int(hit, "order_in_doc")
    hit_block_type = _metadata_text(hit, "block_type")
    return {
        "hit_chunk_id": hit_chunk_id,
        "window_chunk_ids": window_chunk_ids,
        "page_start": page_start,
        "page_end": page_end,
        "section_title": section_title,
        "block_types": block_types,
        "table_id": _metadata_text(hit, "table_id"),
        "hit_order_in_doc": hit_order_in_doc,
        "hit_block_type": hit_block_type,
        "hit_page": hit_page,
        "is_windowed": is_windowed,
        "is_hit_only_fallback": is_hit_only_fallback,
        "citation_label": _build_citation_label(
            page_start=page_start,
            page_end=page_end,
            section_title=section_title,
            block_types=block_types,
        ),
        "evidence_preview": _build_evidence_preview(text),
        "window_chunk_count": window_chunk_count,
        "hit_in_window": hit_in_window,
        "evidence_window_reason": evidence_window_reason,
    }


def _build_citation_label(
    *,
    page_start: int | None,
    page_end: int | None,
    section_title: str | None,
    block_types: tuple[str, ...],
) -> str | None:
    page_label = _page_label(page_start, page_end)
    normalized_block_types = {block_type.strip().lower() for block_type in block_types}
    if normalized_block_types & {"table", "caption"}:
        return "Table / Caption" + (f" · {page_label}" if page_label else "")
    section_label = _truncate_label(section_title)
    if section_label and page_label:
        return f"{section_label} · {page_label}"
    return section_label or page_label


def _page_label(page_start: int | None, page_end: int | None) -> str | None:
    if page_start is None and page_end is None:
        return None
    if page_start is None:
        return f"p.{page_end}"
    if page_end is None or page_end == page_start:
        return f"p.{page_start}"
    return f"pp.{page_start}-{page_end}"


def _truncate_label(value: str | None) -> str | None:
    if not value:
        return None
    normalized = " ".join(value.split())
    if len(normalized) <= CITATION_LABEL_SECTION_LIMIT:
        return normalized
    return normalized[: CITATION_LABEL_SECTION_LIMIT - 3].rstrip() + "..."


def _build_evidence_preview(text: str) -> str | None:
    normalized = " ".join(text.split())
    if not normalized:
        return None
    if len(normalized) <= EVIDENCE_PREVIEW_LIMIT:
        return normalized
    return normalized[: EVIDENCE_PREVIEW_LIMIT - 3].rstrip() + "..."


def _build_window(hit: RetrievedChunk, neighbor_loader: NeighborLoader) -> EvidenceWindow:
    block_type = _block_type(hit)
    if block_type == "heading":
        chunks = _safe_neighbors(hit, neighbor_loader, before=0, after=2)
        selected = _select_heading_window(hit, chunks)
        return EvidenceWindow(hit=hit, chunks=tuple(selected), reason="heading_following")

    if block_type in {"table", "caption"}:
        chunks = _safe_neighbors(hit, neighbor_loader, before=1, after=1)
        selected = _select_table_caption_window(hit, chunks)
        return EvidenceWindow(hit=hit, chunks=tuple(selected), reason="table_caption")

    chunks = _safe_neighbors(hit, neighbor_loader, before=1, after=1)
    selected = _select_neighbor_window(hit, chunks)
    return EvidenceWindow(hit=hit, chunks=tuple(selected), reason="neighbor")


def _safe_neighbors(
    hit: RetrievedChunk,
    neighbor_loader: NeighborLoader,
    *,
    before: int,
    after: int,
) -> list[RetrievedChunk]:
    try:
        chunks = neighbor_loader(hit, before, after)
    except Exception:
        return [hit]
    return chunks or [hit]


def _select_heading_window(hit: RetrievedChunk, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    ordered = _sorted_unique_chunks(chunks, fallback_hit=hit)
    following = [
        chunk
        for chunk in ordered
        if _chunk_order(chunk) is not None
        and _chunk_order(hit) is not None
        and _chunk_order(chunk) > _chunk_order(hit)
        and _is_body_like(chunk)
        and _same_section_or_unknown(hit, chunk)
        and not _is_reference_like(chunk)
    ]
    selected = [hit] + following[:2]
    return _cap_window(selected, primary_hit=hit)


def _select_table_caption_window(hit: RetrievedChunk, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    ordered = _sorted_unique_chunks(chunks, fallback_hit=hit)
    hit_table_id = _metadata_text(hit, "table_id") or hit.anchor
    selected: list[RetrievedChunk] = []
    for chunk in ordered:
        if chunk.chunk_id == hit.chunk_id:
            selected.append(chunk)
            continue
        block_type = _block_type(chunk)
        chunk_table_id = _metadata_text(chunk, "table_id") or chunk.anchor
        same_table = bool(hit_table_id and chunk_table_id and hit_table_id == chunk_table_id)
        adjacent_context = block_type in {"table", "caption"} and _same_section_or_unknown(hit, chunk)
        if same_table or adjacent_context:
            selected.append(chunk)
    return _cap_window(selected or [hit], primary_hit=hit)


def _select_neighbor_window(hit: RetrievedChunk, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    ordered = _sorted_unique_chunks(chunks, fallback_hit=hit)
    selected = [
        chunk
        for chunk in ordered
        if chunk.chunk_id == hit.chunk_id or _is_safe_neighbor(hit, chunk)
    ]
    return _cap_window(selected or [hit], primary_hit=hit)


def _is_safe_neighbor(hit: RetrievedChunk, chunk: RetrievedChunk) -> bool:
    if hit.doc_id != chunk.doc_id:
        return False
    if not _same_section_or_unknown(hit, chunk):
        return False
    if _block_type(chunk) == "heading":
        return False
    if _is_reference_like(chunk):
        return False
    return True


def _same_section_or_unknown(left: RetrievedChunk, right: RetrievedChunk) -> bool:
    left_section = (_metadata_text(left, "section_title") or left.section or "").strip()
    right_section = (_metadata_text(right, "section_title") or right.section or "").strip()
    return not left_section or not right_section or left_section == right_section


def _is_body_like(chunk: RetrievedChunk) -> bool:
    return _block_type(chunk) in {"paragraph", "list_item", "other", ""}


def _is_reference_like(chunk: RetrievedChunk) -> bool:
    section = (_metadata_text(chunk, "section_title") or chunk.section or "").strip().lower()
    return section in {"references", "reference", "bibliography"} or section.startswith("references")


def _block_type(hit: RetrievedChunk) -> str:
    return (_metadata_text(hit, "block_type") or "").strip().lower()


def _cap_window(
    chunks: list[RetrievedChunk],
    *,
    primary_hit: RetrievedChunk | None = None,
) -> list[RetrievedChunk]:
    ordered = _sorted_unique_chunks(chunks, fallback_hit=primary_hit)
    if not ordered:
        return [primary_hit] if primary_hit is not None else []

    primary = primary_hit or ordered[0]
    primary_chunk = _find_chunk_by_id(ordered, primary.chunk_id) or primary
    capped: list[RetrievedChunk] = [primary_chunk]
    total_chars = len(primary_chunk.citation_text().strip())
    if total_chars >= MAX_EVIDENCE_WINDOW_CHARS or len(capped) >= MAX_EVIDENCE_WINDOW_BLOCKS:
        return capped

    candidates = [chunk for chunk in ordered if chunk.chunk_id != primary_chunk.chunk_id]
    candidates.sort(key=lambda chunk: (_order_distance(primary_chunk, chunk), _chunk_order(chunk) or 10**9, chunk.chunk_id))
    for chunk in candidates:
        text = chunk.citation_text().strip()
        next_chars = total_chars + len(text)
        if len(capped) >= MAX_EVIDENCE_WINDOW_BLOCKS:
            break
        if next_chars > MAX_EVIDENCE_WINDOW_CHARS:
            continue
        capped.append(chunk)
        total_chars = next_chars

    return _sorted_unique_chunks(capped, fallback_hit=primary_chunk)


def _merge_overlapping_windows(windows: list[EvidenceWindow]) -> list[EvidenceWindow]:
    merged: list[EvidenceWindow] = []
    for window in windows:
        chunk_ids = set(window.chunk_ids)
        if not chunk_ids:
            merged.append(window)
            continue
        match_index = next(
            (
                index
                for index, existing in enumerate(merged)
                if existing.hit.doc_id == window.hit.doc_id and chunk_ids.intersection(existing.chunk_ids)
            ),
            None,
        )
        if match_index is None:
            merged.append(window)
            continue
        existing = merged[match_index]
        combined = _cap_window([*existing.chunks, *window.chunks], primary_hit=existing.hit)
        if existing.hit.chunk_id and existing.hit.chunk_id not in {chunk.chunk_id for chunk in combined}:
            combined = [existing.hit]
        merged[match_index] = EvidenceWindow(
            hit=existing.hit,
            chunks=tuple(combined),
            reason="merged",
        )
    return merged


def _sorted_unique_chunks(
    chunks: list[RetrievedChunk],
    *,
    fallback_hit: RetrievedChunk | None = None,
) -> list[RetrievedChunk]:
    by_id: dict[str, RetrievedChunk] = {}
    for chunk in chunks:
        if chunk.chunk_id:
            by_id[chunk.chunk_id] = chunk
    if fallback_hit is not None and fallback_hit.chunk_id not in by_id:
        by_id[fallback_hit.chunk_id] = fallback_hit
    return sorted(by_id.values(), key=lambda chunk: (_chunk_order(chunk) if _chunk_order(chunk) is not None else 10**9, chunk.chunk_id))


def _chunk_order(hit: RetrievedChunk) -> int | None:
    order = _metadata_int(hit, "order_in_doc")
    if order is not None:
        return order
    _, _, suffix = hit.chunk_id.rpartition(":")
    if suffix.isdigit():
        return int(suffix)
    return None


def _find_chunk_by_id(chunks: list[RetrievedChunk], chunk_id: str) -> RetrievedChunk | None:
    return next((chunk for chunk in chunks if chunk.chunk_id == chunk_id), None)


def _order_distance(left: RetrievedChunk, right: RetrievedChunk) -> int:
    left_order = _chunk_order(left)
    right_order = _chunk_order(right)
    if left_order is None or right_order is None:
        return 10**9
    return abs(left_order - right_order)


def _normalize_query(query: str) -> str:
    return " ".join(query.lower().strip().split())


def _query_tokens(query: str) -> set[str]:
    tokens: set[str] = set()
    for token in _query_terms(query):
        tokens.update(_token_variants(token))
    return tokens


def _query_terms(query: str) -> set[str]:
    terms: set[str] = set()
    for token in re.findall(r"[a-z0-9]+", query.lower()):
        if len(token) < 3 or token in _QUERY_STOPWORDS:
            continue
        terms.add(token)
    return terms


def _expanded_terms(text: str) -> set[str]:
    terms: set[str] = set()
    for token in re.findall(r"[a-z0-9]+", text.lower()):
        if len(token) < 3:
            continue
        terms.update(_token_variants(token))
    return terms


def _expand_term_set(terms: set[str]) -> set[str]:
    expanded: set[str] = set()
    for term in terms:
        expanded.update(_token_variants(term))
    return expanded


def _core_query_terms(query_terms: set[str]) -> set[str]:
    core = {term for term in query_terms if term not in _WEAK_ALIGNMENT_TERMS}
    return core or set(query_terms)


def _is_open_domain_sensitive_query(query_terms: set[str]) -> bool:
    expanded = _expand_term_set(query_terms)
    return bool(expanded & _OPEN_DOMAIN_SENSITIVE_TERMS)


def _source_count(hits: list[RetrievedChunk]) -> int:
    sources = {
        hit.source or hit.doc_id or hit.chunk_id
        for hit in hits
        if hit.source or hit.doc_id or hit.chunk_id
    }
    return len(sources)


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
