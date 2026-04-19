"""Formal retrieval, citation, and grounded-answer domain models."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum

from ports.llm import EvidenceItem


@dataclass(frozen=True)
class RetrievalFilters:
    """Controlled retrieval filters shared by search/chat/summarize."""

    sources: tuple[str, ...] = ()
    source_types: tuple[str, ...] = ()
    section: str | None = None
    title_contains: str | None = None
    requested_url_contains: str | None = None
    page_from: int | None = None
    page_to: int | None = None

    def normalized_single_source(self) -> str | None:
        return self.sources[0] if len(self.sources) == 1 else None

    def normalized_single_source_type(self) -> str | None:
        return self.source_types[0] if len(self.source_types) == 1 else None

    def matches_metadata(self, metadata: dict[str, object]) -> bool:
        source = str(metadata.get("source") or metadata.get("source_path") or "").strip()
        source_type = str(metadata.get("source_type") or "").strip()
        section = str(metadata.get("section") or "").strip()
        title = str(metadata.get("title") or "").strip().lower()
        requested_url = str(metadata.get("requested_url") or "").strip().lower()

        if self.sources and source not in self.sources:
            return False
        if self.source_types and source_type not in self.source_types:
            return False
        if self.section and section != self.section:
            return False
        if self.title_contains and self.title_contains.lower() not in title:
            return False
        if self.requested_url_contains and self.requested_url_contains.lower() not in requested_url:
            return False

        page = _parse_page(metadata.get("page"))
        if self.page_from is not None:
            if page is None or page < self.page_from:
                return False
        if self.page_to is not None:
            if page is None or page > self.page_to:
                return False
        return True


@dataclass(frozen=True)
class CitationRecord:
    """Traceable citation record for one retrieved chunk."""

    doc_id: str
    chunk_id: str
    source: str
    snippet: str
    page: int | None = None
    anchor: str | None = None
    title: str | None = None
    section: str | None = None
    location: str | None = None
    ref: str | None = None
    # Fine-grained citation support
    block_id: str | None = None               # Specific block within the chunk
    highlighted_sentence: str | None = None    # Exact matching sentence text
    position_start: int | None = None          # Character offset start within chunk
    position_end: int | None = None            # Character offset end within chunk
    section_path: str | None = None            # Hierarchical section path like "1.2.3"

    def to_api_dict(self) -> dict[str, str | int | None]:
        return {
            "doc_id": self.doc_id,
            "chunk_id": self.chunk_id,
            "source": self.source,
            "snippet": self.snippet,
            "page": self.page,
            "anchor": self.anchor,
            "title": self.title,
            "section": self.section,
            "location": self.location,
            "ref": self.ref,
            "block_id": self.block_id,
            "highlighted_sentence": self.highlighted_sentence,
            "position_start": self.position_start,
            "position_end": self.position_end,
            "section_path": self.section_path,
        }


class SupportStatus(StrEnum):
    """Support level for one grounded answer."""

    SUPPORTED = "supported"
    PARTIALLY_SUPPORTED = "partially_supported"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    CONFLICTING_EVIDENCE = "conflicting_evidence"


class RefusalReason(StrEnum):
    """Reason why a grounded answer refused or downgraded generation."""

    NO_RELEVANT_EVIDENCE = "no_relevant_evidence"
    INSUFFICIENT_CONTEXT = "insufficient_context"
    CONFLICTING_SOURCES = "conflicting_sources"
    OUT_OF_SCOPE = "out_of_scope"


class EvidenceFreshness(StrEnum):
    """Freshness state of one evidence item against the current source state."""

    FRESH = "fresh"
    STALE_POSSIBLE = "stale_possible"
    INVALIDATED = "invalidated"


@dataclass(frozen=True)
class EvidenceObject:
    """Stable machine-consumable evidence object derived from one retrieved chunk."""

    doc_id: str
    chunk_id: str
    source: str
    snippet: str
    page: int | None = None
    anchor: str | None = None
    title: str | None = None
    section: str | None = None
    location: str | None = None
    ref: str | None = None
    score: float | None = None
    source_version: str | None = None
    content_hash: str | None = None
    freshness: EvidenceFreshness = EvidenceFreshness.FRESH
    # Fine-grained citation support
    block_id: str | None = None               # Specific block within the chunk
    highlighted_sentence: str | None = None    # Exact matching sentence text
    position_start: int | None = None          # Character offset start within chunk
    position_end: int | None = None            # Character offset end within chunk
    section_path: str | None = None            # Hierarchical section path like "1.2.3"

    def to_api_dict(self) -> dict[str, object]:
        return {
            "doc_id": self.doc_id,
            "chunk_id": self.chunk_id,
            "source": self.source,
            "page": self.page,
            "anchor": self.anchor,
            "title": self.title,
            "section": self.section,
            "location": self.location,
            "ref": self.ref,
            "snippet": self.snippet,
            "score": self.score,
            "source_version": self.source_version,
            "content_hash": self.content_hash,
            "freshness": self.freshness.value,
            "block_id": self.block_id,
            "highlighted_sentence": self.highlighted_sentence,
            "position_start": self.position_start,
            "position_end": self.position_end,
            "section_path": self.section_path,
        }


@dataclass(frozen=True)
class GroundedAnswer:
    """Grounded answer or summary result with explicit support semantics."""

    answer: str
    evidence: tuple[EvidenceObject, ...] = ()
    support_status: SupportStatus = SupportStatus.SUPPORTED
    refusal_reason: RefusalReason | None = None

    def to_api_dict(self) -> dict[str, object]:
        return {
            "answer": self.answer,
            "evidence": [item.to_api_dict() for item in self.evidence],
            "support_status": self.support_status.value,
            "refusal_reason": None if self.refusal_reason is None else self.refusal_reason.value,
        }


@dataclass(frozen=True)
class ComparedPoint:
    """One grounded compare statement with paired evidence from each side."""

    statement: str
    left_evidence: tuple[EvidenceObject, ...] = ()
    right_evidence: tuple[EvidenceObject, ...] = ()
    summary_note: str | None = None

    def to_api_dict(self) -> dict[str, object]:
        return {
            "statement": self.statement,
            "left_evidence": [item.to_api_dict() for item in self.left_evidence],
            "right_evidence": [item.to_api_dict() for item in self.right_evidence],
            "summary_note": self.summary_note,
        }


@dataclass(frozen=True)
class GroundedCompareResult:
    """Stable grounded compare payload for direct APIs and unified execution."""

    query: str
    common_points: tuple[ComparedPoint, ...] = ()
    differences: tuple[ComparedPoint, ...] = ()
    conflicts: tuple[ComparedPoint, ...] = ()
    support_status: SupportStatus = SupportStatus.SUPPORTED
    refusal_reason: RefusalReason | None = None

    def to_api_dict(self) -> dict[str, object]:
        return {
            "query": self.query,
            "common_points": [item.to_api_dict() for item in self.common_points],
            "differences": [item.to_api_dict() for item in self.differences],
            "conflicts": [item.to_api_dict() for item in self.conflicts],
            "support_status": self.support_status.value,
            "refusal_reason": None if self.refusal_reason is None else self.refusal_reason.value,
        }


@dataclass(frozen=True)
class RetrievedChunk:
    """Normalized retrieval hit used across services, postprocess, and citations."""

    text: str
    doc_id: str
    chunk_id: str
    source: str
    source_type: str = "file"
    title: str = ""
    section: str = ""
    location: str = ""
    ref: str = ""
    page: int | None = None
    anchor: str | None = None
    distance: float | None = None
    original_text: str | None = None
    compressed_text: str | None = None
    rerank_score: float | None = None
    retrieval_rank: int | None = None
    compression_applied: bool = False
    requested_url: str | None = None
    final_url: str | None = None
    status_code: int | None = None
    fetched_at: str | None = None
    ssl_verified: bool | None = None
    extra_metadata: dict[str, object] = field(default_factory=dict)

    def prompt_text(self) -> str:
        return self.compressed_text or self.text

    def citation_text(self) -> str:
        return self.original_text or self.text

    def with_updates(self, **changes) -> "RetrievedChunk":
        return replace(self, **changes)

    @classmethod
    def from_raw(cls, text: str, metadata: dict[str, object], distance: float | None = None) -> "RetrievedChunk":
        source = str(metadata.get("source") or metadata.get("source_path") or "")
        title = str(metadata.get("title") or "")
        section = str(metadata.get("section") or "")
        location = str(metadata.get("location") or metadata.get("section") or source)
        ref = str(metadata.get("ref") or title or source)
        return cls(
            text=text,
            doc_id=str(metadata.get("doc_id", "")),
            chunk_id=str(metadata.get("chunk_id", "")),
            source=source,
            source_type=str(metadata.get("source_type") or "file"),
            title=title,
            section=section,
            location=location,
            ref=ref,
            page=_parse_page(metadata.get("page")),
            anchor=_normalize_optional_text(metadata.get("anchor")),
            distance=float(distance) if distance is not None else None,
            requested_url=_normalize_optional_text(metadata.get("requested_url")),
            final_url=_normalize_optional_text(metadata.get("final_url")),
            status_code=_parse_page(metadata.get("status_code")),
            fetched_at=_normalize_optional_text(metadata.get("fetched_at")),
            ssl_verified=_parse_bool(metadata.get("ssl_verified")),
            extra_metadata={
                key: value
                for key, value in metadata.items()
                if key not in {
                    "doc_id",
                    "chunk_id",
                    "source",
                    "source_path",
                    "source_type",
                    "title",
                    "section",
                    "location",
                    "ref",
                    "page",
                    "anchor",
                    "requested_url",
                    "final_url",
                    "status_code",
                    "fetched_at",
                    "ssl_verified",
                }
            },
        )


@dataclass(frozen=True)
class SearchHitRecord:
    """Search hit returned to the API after citation binding."""

    chunk: RetrievedChunk
    citation: CitationRecord

    def to_api_dict(self) -> dict[str, object]:
        return {
            "text": self.chunk.text,
            "doc_id": self.chunk.doc_id,
            "chunk_id": self.chunk.chunk_id,
            "source": self.chunk.source,
            "distance": self.chunk.distance,
            "citation": self.citation.to_api_dict(),
        }


@dataclass(frozen=True)
class SearchResult:
    """Formal search result returned by SearchService."""

    query: str
    top_k: int
    hits: list[SearchHitRecord]

    def to_api_dict(self) -> dict[str, object]:
        return {
            "query": self.query,
            "top_k": self.top_k,
            "hits": [hit.to_api_dict() for hit in self.hits],
        }


@dataclass(frozen=True)
class GroundedSelectionResult:
    """Grounded evidence selection after threshold filtering."""

    hits: list[RetrievedChunk]


@dataclass(frozen=True)
class ContextBlock:
    """Prompt-ready context assembled from retrieved chunks."""

    chunks: list[RetrievedChunk]

    def to_evidence_items(self) -> list[EvidenceItem]:
        return [
            {
                "chunk_id": chunk.chunk_id,
                "source": chunk.source,
                "title": chunk.title,
                "section": chunk.section,
                "location": chunk.location,
                "ref": chunk.ref,
                "text": chunk.prompt_text(),
            }
            for chunk in self.chunks
        ]

    def to_text(self) -> str:
        evidence = self.to_evidence_items()
        if not evidence:
            return "(no evidence provided)"

        lines: list[str] = []
        for item in evidence:
            ref = str(item.get("ref") or item.get("source") or item.get("chunk_id") or "").strip()
            chunk_id = str(item.get("chunk_id", "")).strip()
            text = str(item.get("text", "")).strip().replace("\n", " ")
            lines.append(f"[{ref} | {chunk_id}] {text}")
        return "\n".join(lines)


def _normalize_optional_text(value: object) -> str | None:
    if value is None:
        return None
    return str(value).strip()


def _parse_page(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_bool(value: object) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    return None
