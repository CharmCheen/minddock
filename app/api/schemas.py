"""Pydantic schemas for API requests and responses."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.application.artifacts import (
    BaseArtifact,
    MermaidArtifact,
    SearchResultsArtifact,
    SkillResultArtifact,
    StructuredJsonArtifact,
    TextArtifact,
)
from app.application.client_events import (
    ClientArtifactPayload,
    ClientCompletedPayload,
    ClientEvent,
    ClientFailedPayload,
    ClientHeartbeatPayload,
    ClientProgressPayload,
    ClientRunStartedPayload,
    ClientWarningPayload,
)
from app.application.events import (
    ArtifactEmittedPayload,
    ExecutionEvent,
    ExecutionEventKind,
    ExecutionMetadataDelta,
    MetadataUpdatedPayload,
    PlanBuiltPayload,
    RunCompletedPayload,
    RunFailedPayload,
    RunStartedPayload,
    StepCompletedPayload,
    StepStartedPayload,
    WarningEmittedPayload,
)
from app.application.models import (
    CitationPolicy,
    ExecutionPolicy,
    OutputMode,
    SkillPolicyMode,
    TaskType,
    UnifiedExecutionRequest,
    UnifiedExecutionResponse,
)
from app.skills.manifest import SkillInfo, SkillManifestValidationResult
from app.skills.models import SkillCatalogDetail, SkillCatalogEntry, SkillInputSchema, SkillOutputSchema, SkillSchemaField
from app.runtime.models import (
    LocalityPreference,
    OptimizationTarget,
    RuntimeProfileSummary,
    RuntimeSelectionMode,
)
from app.rag.retrieval_models import (
    CitationRecord,
    ComparedPoint,
    EvidenceFreshness,
    EvidenceObject,
    GroundedAnswer,
    GroundedCompareResult,
    RefusalReason,
    RetrievalFilters,
    SearchHitRecord,
    SearchResult,
    SupportStatus,
)
from app.rag.source_models import (
    DeleteSourceResult,
    FailedSourceInfo,
    IngestBatchResult,
    SourceCatalogEntry,
    SourceChunkPreview,
    SourceDetail,
    SourceState,
)
from app.services.service_models import (
    CatalogServiceResult,
    ChatServiceResult,
    CompareServiceResult,
    DeleteSourceServiceResult,
    IngestServiceResult,
    ReingestSourceServiceResult,
    SearchServiceResult,
    SourceDetailServiceResult,
    SourceInspectServiceResult,
    SummarizeServiceResult,
)


class MetadataFilters(BaseModel):
    """Minimal metadata filters shared by search and chat endpoints."""

    source: str | list[str] | None = Field(default=None, description="Filter by one or more document sources")
    section: str | None = Field(default=None, description="Filter by section heading")
    source_type: Literal["file", "url"] | list[Literal["file", "url"]] | None = Field(
        default=None,
        description="Filter by one or more source kinds. File covers local md/txt/pdf sources; url covers fetched web pages.",
    )
    title_contains: str | None = Field(default=None, description="Case-insensitive contains match on title metadata")
    requested_url_contains: str | None = Field(
        default=None,
        description="Case-insensitive contains match on the original requested URL metadata",
    )
    page_from: int | None = Field(default=None, ge=1, description="Lower bound for PDF page filtering")
    page_to: int | None = Field(default=None, ge=1, description="Upper bound for PDF page filtering")

    @field_validator("section", "title_contains", "requested_url_contains")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("source")
    @classmethod
    def normalize_source_values(cls, value: str | list[str] | None) -> str | list[str] | None:
        return cls._normalize_text_or_list(value)

    @field_validator("source_type")
    @classmethod
    def normalize_source_type_values(
        cls,
        value: Literal["file", "url"] | list[Literal["file", "url"]] | None,
    ) -> Literal["file", "url"] | list[Literal["file", "url"]] | None:
        return cls._normalize_text_or_list(value)

    @model_validator(mode="after")
    def validate_page_range(self) -> "MetadataFilters":
        if self.page_from is not None and self.page_to is not None and self.page_from > self.page_to:
            raise ValueError("page_from must be less than or equal to page_to")
        return self

    def to_retrieval_filters(self) -> RetrievalFilters:
        return RetrievalFilters(
            sources=_ensure_tuple(self.source),
            source_types=_ensure_tuple(self.source_type),
            section=self.section,
            title_contains=self.title_contains,
            requested_url_contains=self.requested_url_contains,
            page_from=self.page_from,
            page_to=self.page_to,
        )

    @staticmethod
    def _normalize_text_or_list(value):
        if value is None:
            return None
        if isinstance(value, list):
            normalized = [str(item).strip() for item in value if str(item).strip()]
            return normalized or None
        normalized = str(value).strip()
        return normalized or None


# ---------------------------------------------------------------------------
# Citation
# ---------------------------------------------------------------------------

class CitationItem(BaseModel):
    """Standardized citation bound to a retrieved chunk.

    Required fields: doc_id, chunk_id, source, snippet.
    Optional fields preserved for compatibility and future expansion.
    """

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
    hit_chunk_id: str | None = None
    window_chunk_ids: list[str] = Field(default_factory=list)
    page_start: int | None = None
    page_end: int | None = None
    section_title: str | None = None
    block_types: list[str] = Field(default_factory=list)
    table_id: str | None = None
    hit_order_in_doc: int | None = None
    hit_block_type: str | None = None
    hit_page: int | None = None
    is_windowed: bool = False
    is_hit_only_fallback: bool = False
    citation_label: str | None = None
    evidence_preview: str | None = None
    window_chunk_count: int = 0
    hit_in_window: bool = False
    evidence_window_reason: str | None = None

    @classmethod
    def from_record(cls, record: CitationRecord | Mapping[str, object]) -> "CitationItem":
        if isinstance(record, CitationRecord):
            return cls(**record.to_api_dict())
        return cls(**dict(record))


class EvidenceItem(BaseModel):
    """Stable machine-consumable evidence object."""

    doc_id: str
    chunk_id: str
    source: str
    snippet: str
    page: int | None = None
    anchor: str | None = None
    score: float | None = None
    source_version: str | None = None
    content_hash: str | None = None
    freshness: Literal["fresh", "stale_possible", "invalidated"] = "fresh"
    hit_chunk_id: str | None = None
    window_chunk_ids: list[str] = Field(default_factory=list)
    page_start: int | None = None
    page_end: int | None = None
    section_title: str | None = None
    block_types: list[str] = Field(default_factory=list)
    table_id: str | None = None
    hit_order_in_doc: int | None = None
    hit_block_type: str | None = None
    hit_page: int | None = None
    is_windowed: bool = False
    is_hit_only_fallback: bool = False
    citation_label: str | None = None
    evidence_preview: str | None = None
    window_chunk_count: int = 0
    hit_in_window: bool = False
    evidence_window_reason: str | None = None

    @classmethod
    def from_record(cls, record: EvidenceObject | Mapping[str, object] | CitationRecord) -> "EvidenceItem":
        if isinstance(record, EvidenceObject):
            return cls(**record.to_api_dict())
        if isinstance(record, CitationRecord):
            data = record.to_api_dict()
            allowed = set(cls.model_fields)
            return cls(**{key: value for key, value in data.items() if key in allowed})
        return cls(**dict(record))


class GroundedAnswerItem(BaseModel):
    """Shared grounded answer payload for unified execution and artifacts."""

    answer: str
    evidence: list[EvidenceItem] = Field(default_factory=list)
    support_status: str
    refusal_reason: str | None = None

    @classmethod
    def from_record(
        cls,
        record: GroundedAnswer | Mapping[str, object],
    ) -> "GroundedAnswerItem":
        if isinstance(record, GroundedAnswer):
            return cls(
                answer=record.answer,
                evidence=[EvidenceItem.from_record(item) for item in record.evidence],
                support_status=record.support_status.value,
                refusal_reason=None if record.refusal_reason is None else record.refusal_reason.value,
            )
        data = dict(record)
        return cls(
            answer=str(data.get("answer", "")),
            evidence=[EvidenceItem.from_record(item) for item in data.get("evidence", [])],
            support_status=str(data.get("support_status") or "supported"),
            refusal_reason=None if data.get("refusal_reason") is None else str(data.get("refusal_reason")),
        )


class ComparedPointItem(BaseModel):
    """Serializable grounded compare point with paired evidence."""

    statement: str
    left_evidence: list[EvidenceItem] = Field(default_factory=list)
    right_evidence: list[EvidenceItem] = Field(default_factory=list)
    summary_note: str | None = None

    @classmethod
    def from_record(cls, record: ComparedPoint | Mapping[str, object]) -> "ComparedPointItem":
        if isinstance(record, ComparedPoint):
            return cls(
                statement=record.statement,
                left_evidence=[EvidenceItem.from_record(item) for item in record.left_evidence],
                right_evidence=[EvidenceItem.from_record(item) for item in record.right_evidence],
                summary_note=record.summary_note,
            )
        data = dict(record)
        return cls(
            statement=str(data.get("statement", "")),
            left_evidence=[EvidenceItem.from_record(item) for item in data.get("left_evidence", [])],
            right_evidence=[EvidenceItem.from_record(item) for item in data.get("right_evidence", [])],
            summary_note=data.get("summary_note"),
        )


class CompareResultItem(BaseModel):
    """Shared grounded compare payload for direct APIs and unified execution."""

    query: str
    common_points: list[ComparedPointItem] = Field(default_factory=list)
    differences: list[ComparedPointItem] = Field(default_factory=list)
    conflicts: list[ComparedPointItem] = Field(default_factory=list)
    support_status: str
    refusal_reason: str | None = None

    @classmethod
    def from_record(cls, record: GroundedCompareResult | Mapping[str, object]) -> "CompareResultItem":
        if isinstance(record, GroundedCompareResult):
            return cls(
                query=record.query,
                common_points=[ComparedPointItem.from_record(item) for item in record.common_points],
                differences=[ComparedPointItem.from_record(item) for item in record.differences],
                conflicts=[ComparedPointItem.from_record(item) for item in record.conflicts],
                support_status=record.support_status.value,
                refusal_reason=None if record.refusal_reason is None else record.refusal_reason.value,
            )
        data = dict(record)
        return cls(
            query=str(data.get("query", "")),
            common_points=[ComparedPointItem.from_record(item) for item in data.get("common_points", [])],
            differences=[ComparedPointItem.from_record(item) for item in data.get("differences", [])],
            conflicts=[ComparedPointItem.from_record(item) for item in data.get("conflicts", [])],
            support_status=str(data.get("support_status") or "supported"),
            refusal_reason=None if data.get("refusal_reason") is None else str(data.get("refusal_reason")),
        )


class SourceStateItem(BaseModel):
    """Serializable current source state."""

    doc_id: str
    source: str
    current_version: str | None = None
    content_hash: str | None = None
    last_ingested_at: str | None = None
    chunk_count: int = 0
    ingest_status: str | None = None

    @classmethod
    def from_state(cls, state: SourceState | None) -> "SourceStateItem | None":
        if state is None:
            return None
        return cls(
            doc_id=state.doc_id,
            source=state.source,
            current_version=state.current_version,
            content_hash=state.content_hash,
            last_ingested_at=state.last_ingested_at,
            chunk_count=state.chunk_count,
            ingest_status=state.ingest_status,
        )


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

class SearchRequest(BaseModel):
    """Request body for the search endpoint."""

    query: str = Field(..., description="Natural language query")
    top_k: int = Field(default=5, ge=1, le=20, description="Number of hits to return")
    filters: MetadataFilters | None = Field(default=None, description="Optional metadata filters")

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        query = value.strip()
        if not query:
            raise ValueError("query must not be empty")
        return query


class SearchHit(BaseModel):
    """Single search result with its embedded citation."""

    text: str
    doc_id: str
    chunk_id: str
    source: str
    source_type: str = Field(default="file", description="Origin of the source, such as file or url")
    title: str | None = Field(default=None, description="Source title when available")
    section: str | None = Field(default=None, description="Section heading when available")
    distance: float | None = None
    citation: CitationItem

    @classmethod
    def from_record(cls, record: SearchHitRecord | Mapping[str, object]) -> "SearchHit":
        if isinstance(record, SearchHitRecord):
            return cls(
                text=record.chunk.text,
                doc_id=record.chunk.doc_id,
                chunk_id=record.chunk.chunk_id,
                source=record.chunk.source,
                source_type=record.chunk.source_type,
                title=record.chunk.title or None,
                section=record.chunk.section or None,
                distance=record.chunk.distance,
                citation=CitationItem.from_record(record.citation),
            )
        data = dict(record)
        citation = data.get("citation")
        if citation is not None:
            data["citation"] = CitationItem.from_record(citation)
        return cls(**data)


class SearchResponse(BaseModel):
    """Response body for the search endpoint."""

    query: str
    top_k: int
    hits: list[SearchHit]

    @classmethod
    def from_result(cls, result: SearchServiceResult | SearchResult | Mapping[str, object]) -> "SearchResponse":
        if isinstance(result, SearchServiceResult):
            result = result.search_result
        if isinstance(result, SearchResult):
            return cls(
                query=result.query,
                top_k=result.top_k,
                hits=[SearchHit.from_record(hit) for hit in result.hits],
            )
        data = dict(result)
        data["hits"] = [SearchHit.from_record(hit) for hit in data.get("hits", [])]
        return cls(**data)

    @classmethod
    def from_search_artifact(
        cls,
        *,
        query: str,
        top_k: int,
        artifact: SearchResultsArtifact,
    ) -> "SearchResponse":
        return cls(
            query=query,
            top_k=top_k,
            hits=[
                SearchHit(
                    text=item.snippet,
                    doc_id=item.doc_id,
                    chunk_id=item.chunk_id,
                    source=item.source,
                    source_type=item.source_type,
                    title=item.title,
                    section=None,
                    distance=item.score,
                    citation=CitationItem(
                        doc_id=item.doc_id,
                        chunk_id=item.chunk_id,
                        source=item.source,
                        snippet=item.snippet,
                        page=item.page,
                        anchor=item.anchor,
                        title=item.title,
                    ),
                )
                for item in artifact.items
            ],
        )


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    """Request body for the chat endpoint."""

    query: str = Field(..., description="Natural language query")
    top_k: int = Field(default=3, ge=1, le=10, description="Number of retrieved chunks")
    filters: MetadataFilters | None = Field(default=None, description="Optional metadata filters")

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        query = value.strip()
        if not query:
            raise ValueError("query must not be empty")
        return query


class ChatResponse(BaseModel):
    """Response body for the chat endpoint."""

    answer: str
    evidence: list[EvidenceItem] = Field(default_factory=list)
    support_status: str = Field(default="supported")
    refusal_reason: str | None = None
    citations: list[CitationItem]
    retrieved_count: int
    mode: str = Field(default="grounded", description="Response production mode for client-side display")
    workflow_trace: dict[str, Any] | None = None

    @classmethod
    def from_result(cls, result: ChatServiceResult | Mapping[str, Any]) -> "ChatResponse":
        if isinstance(result, ChatServiceResult):
            grounded = _resolve_grounded_answer(
                grounded=result.grounded_answer,
                answer=result.answer,
                citations=result.citations,
                insufficient_evidence=result.metadata.insufficient_evidence,
                support_status=result.metadata.support_status,
                refusal_reason=result.metadata.refusal_reason,
            )
            return cls(
                answer=result.answer,
                evidence=list(grounded.evidence),
                support_status=grounded.support_status,
                refusal_reason=grounded.refusal_reason,
                citations=[CitationItem.from_record(item) for item in result.citations],
                retrieved_count=result.metadata.retrieved_count,
                mode=result.metadata.mode or "grounded",
                workflow_trace=result.metadata.workflow_trace,
            )
        grounded = _resolve_grounded_answer(
            grounded=result.get("grounded_answer"),
            answer=str(result.get("answer", "")),
            citations=result.get("citations", []),
            insufficient_evidence=bool(result.get("insufficient_evidence", False)),
            support_status=result.get("support_status"),
            refusal_reason=result.get("refusal_reason"),
        )
        return cls(
            answer=str(result.get("answer", "")),
            evidence=list(grounded.evidence),
            support_status=grounded.support_status,
            refusal_reason=grounded.refusal_reason,
            citations=[CitationItem.from_record(item) for item in result.get("citations", [])],
            retrieved_count=int(result.get("retrieved_count", 0)),
            mode=str(result.get("mode") or "grounded"),
            workflow_trace=result.get("workflow_trace"),
        )


# ---------------------------------------------------------------------------
# Summarize
# ---------------------------------------------------------------------------

class SummarizeRequest(BaseModel):
    """Request body for the summarize endpoint."""

    query: str | None = Field(default=None, description="Summary query or theme")
    topic: str | None = Field(default=None, description="Topic to summarize")
    top_k: int = Field(default=5, ge=1, le=20, description="Number of retrieved chunks")
    filters: MetadataFilters | None = Field(default=None, description="Optional metadata filters")
    mode: Literal["basic", "map_reduce"] = Field(
        default="basic",
        description="Summarization mode; map_reduce summarizes grouped evidence before reduction.",
    )
    output_format: Literal["text", "mermaid"] = Field(
        default="text",
        description="Optional structured output format.",
    )

    @field_validator("query", "topic")
    @classmethod
    def normalize_summary_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def validate_topic_or_query(self) -> "SummarizeRequest":
        if not self.query and not self.topic:
            raise ValueError("either query or topic must be provided")
        return self

    def resolved_topic(self) -> str:
        return self.topic or self.query or ""


class SummarizeResponse(BaseModel):
    """Response body for the summarize endpoint."""

    summary: str
    evidence: list[EvidenceItem] = Field(default_factory=list)
    support_status: str = "supported"
    refusal_reason: str | None = None
    citations: list[CitationItem]
    retrieved_count: int
    mode: str = "basic"
    output_format: str = "text"
    structured_output: str | None = None
    workflow_trace: dict[str, Any] | None = None

    @classmethod
    def from_result(cls, result: SummarizeServiceResult | Mapping[str, Any]) -> "SummarizeResponse":
        if isinstance(result, SummarizeServiceResult):
            grounded = _resolve_grounded_answer(
                grounded=result.grounded_answer,
                answer=result.summary,
                citations=result.citations,
                insufficient_evidence=result.metadata.insufficient_evidence,
                support_status=result.metadata.support_status,
                refusal_reason=result.metadata.refusal_reason,
            )
            return cls(
                summary=result.summary,
                evidence=list(grounded.evidence),
                support_status=grounded.support_status,
                refusal_reason=grounded.refusal_reason,
                citations=[CitationItem.from_record(item) for item in result.citations],
                retrieved_count=result.metadata.retrieved_count,
                mode=result.metadata.mode or "basic",
                output_format=result.metadata.output_format or "text",
                structured_output=result.structured_output,
                workflow_trace=result.metadata.workflow_trace,
            )
        grounded = _resolve_grounded_answer(
            grounded=result.get("grounded_answer"),
            answer=str(result.get("summary", "")),
            citations=result.get("citations", []),
            insufficient_evidence=bool(result.get("insufficient_evidence", False)),
            support_status=result.get("support_status"),
            refusal_reason=result.get("refusal_reason"),
        )
        return cls(
            summary=str(result.get("summary", "")),
            evidence=list(grounded.evidence),
            support_status=grounded.support_status,
            refusal_reason=grounded.refusal_reason,
            citations=[CitationItem.from_record(item) for item in result.get("citations", [])],
            retrieved_count=int(result.get("retrieved_count", 0)),
            mode=str(result.get("mode") or "basic"),
            output_format=str(result.get("output_format") or "text"),
            structured_output=result.get("structured_output"),
            workflow_trace=result.get("workflow_trace"),
        )


# ---------------------------------------------------------------------------
# Compare
# ---------------------------------------------------------------------------

class CompareRequest(BaseModel):
    """Request body for the grounded compare endpoint."""

    question: str = Field(..., description="Comparison question to evaluate across multiple documents")
    top_k: int = Field(default=6, ge=2, le=20, description="Number of retrieved chunks considered for comparison")
    filters: MetadataFilters | None = Field(default=None, description="Optional retrieval filters; source lists work best for compare")

    @field_validator("question")
    @classmethod
    def validate_question(cls, value: str) -> str:
        question = value.strip()
        if not question:
            raise ValueError("question must not be empty")
        return question


class CompareResponse(BaseModel):
    """Response body for the grounded compare endpoint."""

    query: str
    common_points: list[ComparedPointItem] = Field(default_factory=list)
    differences: list[ComparedPointItem] = Field(default_factory=list)
    conflicts: list[ComparedPointItem] = Field(default_factory=list)
    support_status: str = "supported"
    refusal_reason: str | None = None
    citations: list[CitationItem] = Field(default_factory=list)
    retrieved_count: int = 0
    mode: str = "grounded_compare"
    workflow_trace: dict[str, Any] | None = None

    @classmethod
    def from_result(cls, result: CompareServiceResult | Mapping[str, Any]) -> "CompareResponse":
        if isinstance(result, CompareServiceResult):
            compare = CompareResultItem.from_record(result.compare_result)
            return cls(
                query=compare.query,
                common_points=compare.common_points,
                differences=compare.differences,
                conflicts=compare.conflicts,
                support_status=compare.support_status,
                refusal_reason=compare.refusal_reason,
                citations=[CitationItem.from_record(item) for item in result.citations],
                retrieved_count=result.metadata.retrieved_count,
                mode=result.metadata.mode or "grounded_compare",
                workflow_trace=result.metadata.workflow_trace,
            )
        compare = CompareResultItem.from_record(result)
        return cls(
            query=compare.query,
            common_points=compare.common_points,
            differences=compare.differences,
            conflicts=compare.conflicts,
            support_status=compare.support_status,
            refusal_reason=compare.refusal_reason,
            citations=[CitationItem.from_record(item) for item in result.get("citations", [])],
            retrieved_count=int(result.get("retrieved_count", 0)),
            mode=str(result.get("mode") or "grounded_compare"),
            workflow_trace=result.get("workflow_trace"),
        )


# ---------------------------------------------------------------------------
# Ingest
# ---------------------------------------------------------------------------

class IngestRequest(BaseModel):
    """Request body for the ingest endpoint."""

    rebuild: bool = Field(default=False, description="Delete existing index before re-ingesting")
    urls: list[str] = Field(
        default_factory=list,
        description="Optional HTTP/HTTPS URLs to fetch and ingest alongside the local knowledge base.",
    )

    @field_validator("urls")
    @classmethod
    def validate_urls(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        for item in value:
            url = item.strip()
            if not url:
                continue
            if not (url.startswith("http://") or url.startswith("https://")):
                raise ValueError("ingest urls must start with http:// or https://")
            normalized.append(url)
        return normalized


class SourceCatalogQueryParams(BaseModel):
    """Query parameters for source catalog listing."""

    source_type: Literal["file", "url"] | None = Field(default=None, description="Optional source-type filter")


class SourceLookupParams(BaseModel):
    """Query parameters for source lookup by exact source string."""

    source: str = Field(..., description="Exact source identifier to resolve")

    @field_validator("source")
    @classmethod
    def validate_source(cls, value: str) -> str:
        source = value.strip()
        if not source:
            raise ValueError("source must not be empty")
        return source


class SourceInspectQueryParams(BaseModel):
    """Query parameters for source chunk preview inspection."""

    limit: int = Field(default=10, ge=1, le=100, description="Maximum number of chunk previews to return")
    offset: int = Field(default=0, ge=0, description="Number of chunks to skip before collecting previews")
    include_admin_metadata: bool = Field(
        default=False,
        description="When true, include a controlled admin/debug metadata block for inspection use",
    )


class SourceCatalogItem(BaseModel):
    """Aggregated indexed source entry."""

    doc_id: str
    source: str
    source_type: str
    title: str
    chunk_count: int
    sections: list[str] = Field(default_factory=list)
    pages: list[int] = Field(default_factory=list)
    requested_url: str | None = None
    final_url: str | None = None
    source_state: SourceStateItem | None = None
    # URL source enrichment
    domain: str | None = None  # URL sources: netloc; file sources: None
    description: str | None = None  # URL sources: og_description; file sources: None

    @classmethod
    def from_entry(cls, entry: SourceCatalogEntry) -> "SourceCatalogItem":
        return cls(
            doc_id=entry.doc_id,
            source=entry.source,
            source_type=entry.source_type,
            title=entry.title,
            chunk_count=entry.chunk_count,
            sections=list(entry.sections),
            pages=list(entry.pages),
            requested_url=entry.requested_url,
            final_url=entry.final_url,
            source_state=SourceStateItem.from_state(entry.state),
            domain=entry.domain,
            description=entry.description,
        )


class SourceCatalogResponse(BaseModel):
    """Response body for listing indexed sources."""

    items: list[SourceCatalogItem]
    total: int

    @classmethod
    def from_result(cls, result: CatalogServiceResult) -> "SourceCatalogResponse":
        return cls(items=[SourceCatalogItem.from_entry(item) for item in result.entries], total=len(result.entries))


class SourceDetailResponse(BaseModel):
    """Response body for detailed source lookup."""

    found: bool
    item: SourceCatalogItem | None = None
    representative_metadata: dict[str, object] = Field(default_factory=dict)
    admin_metadata: dict[str, object] = Field(default_factory=dict)

    @classmethod
    def from_result(cls, result: SourceDetailServiceResult) -> "SourceDetailResponse":
        if not result.found or result.detail is None:
            return cls(found=False)
        return cls(
            found=True,
            item=SourceCatalogItem.from_entry(result.detail.entry),
            representative_metadata=result.detail.representative_metadata,
            admin_metadata=result.admin_metadata if result.include_admin_metadata else {},
        )


class SourceChunkPreviewItem(BaseModel):
    """Controlled preview of one chunk belonging to a source."""

    chunk_id: str
    chunk_index: int | None = None
    preview_text: str
    title: str
    section: str | None = None
    location: str | None = None
    ref: str | None = None
    page: int | None = None
    anchor: str | None = None
    admin_metadata: dict[str, object] = Field(default_factory=dict)

    @classmethod
    def from_preview(cls, preview: SourceChunkPreview) -> "SourceChunkPreviewItem":
        return cls(
            chunk_id=preview.chunk_id,
            chunk_index=preview.chunk_index,
            preview_text=preview.preview_text,
            title=preview.title,
            section=preview.section,
            location=preview.location,
            ref=preview.ref,
            page=preview.page,
            anchor=preview.anchor,
            admin_metadata=preview.admin_metadata,
        )


class SourceChunkPageResponse(BaseModel):
    """Response body for source chunk preview inspection."""

    found: bool
    item: SourceCatalogItem | None = None
    total_chunks: int = 0
    returned_chunks: int = 0
    limit: int = 0
    offset: int = 0
    chunks: list[SourceChunkPreviewItem] = Field(default_factory=list)
    representative_metadata: dict[str, object] = Field(default_factory=dict)
    admin_metadata: dict[str, object] = Field(default_factory=dict)

    @classmethod
    def from_result(cls, result: SourceInspectServiceResult) -> "SourceChunkPageResponse":
        if not result.found or result.inspect is None:
            return cls(found=False)
        inspect = result.inspect
        return cls(
            found=True,
            item=SourceCatalogItem.from_entry(inspect.detail.entry),
            total_chunks=inspect.chunk_page.total_chunks,
            returned_chunks=inspect.chunk_page.returned_chunks,
            limit=inspect.chunk_page.limit,
            offset=inspect.chunk_page.offset,
            chunks=[SourceChunkPreviewItem.from_preview(item) for item in inspect.chunk_page.chunks],
            representative_metadata=inspect.detail.representative_metadata,
            admin_metadata=inspect.admin_metadata if inspect.include_admin_metadata else {},
        )


class DeleteSourceResponse(BaseModel):
    """Response body for deleting an indexed source."""

    found: bool
    doc_id: str | None = None
    source: str | None = None
    source_type: str | None = None
    deleted_chunks: int = 0

    @classmethod
    def from_result(cls, result: DeleteSourceServiceResult | DeleteSourceResult) -> "DeleteSourceResponse":
        if isinstance(result, DeleteSourceServiceResult):
            result = result.result
        return cls(
            found=result.found,
            doc_id=result.doc_id,
            source=result.source,
            source_type=result.source_type,
            deleted_chunks=result.deleted_chunks,
        )


class ReingestSourceResponse(BaseModel):
    """Response body for reingesting one indexed source."""

    found: bool
    ok: bool = False
    doc_id: str | None = None
    source: str | None = None
    source_type: str | None = None
    chunks_upserted: int = 0
    chunks_deleted: int = 0
    failure: FailedSourceItem | None = None

    @classmethod
    def from_result(cls, result: ReingestSourceServiceResult) -> "ReingestSourceResponse":
        if not result.found or result.source_result is None:
            return cls(found=False)
        failure = FailedSourceItem.from_info(result.source_result.failure) if result.source_result.failure is not None else None
        return cls(
            found=True,
            ok=result.source_result.ok,
            doc_id=result.source_result.descriptor.doc_id,
            source=result.source_result.descriptor.source,
            source_type=result.source_result.descriptor.source_type,
            chunks_upserted=result.source_result.chunks_upserted,
            chunks_deleted=result.source_result.chunks_deleted,
            failure=failure,
        )


class FailedSourceItem(BaseModel):
    """Serializable partial-failure record for ingest responses."""

    source: str = Field(description="Source identifier, such as relative file path or final URL")
    source_type: str = Field(description="Source kind, such as file or url")
    reason: str = Field(description="Human-readable failure reason for this source only")

    @classmethod
    def from_info(cls, info: FailedSourceInfo | Mapping[str, object]) -> "FailedSourceItem":
        if isinstance(info, FailedSourceInfo):
            return cls(**info.to_api_dict())
        return cls(**dict(info))


class IngestResponse(BaseModel):
    """Response body for the ingest endpoint."""

    documents: int = Field(description="Number of source documents processed")
    chunks: int = Field(description="Total chunks written to the vector store")
    ingested_sources: list[str] = Field(
        default_factory=list,
        description="Sources ingested successfully in this request.",
    )
    failed_sources: list[FailedSourceItem] = Field(
        default_factory=list,
        description="Sources that failed but did not abort the whole request.",
    )
    partial_failure: bool = Field(
        default=False,
        description="True when at least one source failed but the overall request still succeeded.",
    )

    @classmethod
    def from_result(cls, result: IngestServiceResult | IngestBatchResult | Mapping[str, object]) -> "IngestResponse":
        if isinstance(result, IngestServiceResult):
            return cls(
                documents=result.documents,
                chunks=result.chunks,
                ingested_sources=result.ingested_sources,
                failed_sources=[FailedSourceItem.from_info(item) for item in result.failed_sources],
                partial_failure=result.metadata.partial_failure,
            )
        if isinstance(result, IngestBatchResult):
            return cls(
                documents=result.documents,
                chunks=result.chunks,
                ingested_sources=result.ingested_sources,
                failed_sources=[FailedSourceItem.from_info(item) for item in result.failed_sources],
                partial_failure=bool(result.failed_sources),
            )
        data = dict(result)
        data["failed_sources"] = [FailedSourceItem.from_info(item) for item in data.get("failed_sources", [])]
        data.setdefault("partial_failure", bool(data["failed_sources"]))
        return cls(**data)


# ---------------------------------------------------------------------------
# Unified execution
# ---------------------------------------------------------------------------

class SkillPolicyItem(BaseModel):
    """Skill policy for unified execution."""

    mode: Literal["disabled", "manual_only", "allowlisted", "planner_allowed", "runtime_native_allowed"] = Field(default="disabled")
    allowlist: list[str] = Field(default_factory=list)
    denied_skill_ids: list[str] = Field(default_factory=list)
    require_public_listing: bool = True
    allow_external_io: bool = False


class ExecutionPolicyItem(BaseModel):
    """Execution policy for profile-based runtime resolution."""

    preferred_profile_id: str | None = None
    allowed_profile_ids: list[str] = Field(default_factory=list)
    selection_mode: Literal["auto", "preferred", "strict"] = "auto"
    optimization_target: Literal["latency", "quality", "cost", "privacy"] = "quality"
    locality_preference: Literal["local_only", "cloud_allowed", "cloud_preferred"] = "cloud_allowed"
    require_skill_support: bool = False
    require_structured_output: bool = False
    require_citations: bool = False

    def to_runtime_policy(self) -> ExecutionPolicy:
        return ExecutionPolicy(
            preferred_profile_id=self.preferred_profile_id,
            allowed_profile_ids=tuple(self.allowed_profile_ids),
            selection_mode=RuntimeSelectionMode(self.selection_mode),
            optimization_target=OptimizationTarget(self.optimization_target),
            locality_preference=LocalityPreference(self.locality_preference),
            require_skill_support=self.require_skill_support,
            require_structured_output=self.require_structured_output,
            require_citations=self.require_citations,
        )


class UnifiedExecutionRequestBody(BaseModel):
    """Request body for the unified frontend execution endpoint."""

    task_type: Literal["chat", "summarize", "search", "compare", "structured_generation"]
    user_input: str = Field(..., description="Primary user task input.")
    top_k: int = Field(default=5, ge=1, le=20, description="Retrieval depth for retrieval-backed tasks.")
    filters: MetadataFilters | None = Field(default=None, description="Optional retrieval filters.")
    execution_policy: ExecutionPolicyItem | None = Field(default=None, description="Execution policy for runtime profile selection.")
    output_mode: Literal["text", "mermaid", "structured"] = Field(default="text")
    citation_policy: Literal["required", "preferred", "none"] = Field(default="preferred")
    skill_policy: SkillPolicyItem = Field(default_factory=SkillPolicyItem)
    requested_skill_id: str | None = Field(default=None, description="Explicitly request one skill to bind into the execution plan.")
    requested_skill_arguments: dict[str, Any] = Field(default_factory=dict, description="Typed arguments for the requested skill.")
    conversation_metadata: dict[str, object] = Field(default_factory=dict)
    task_options: dict[str, object] = Field(default_factory=dict)
    debug: bool = Field(default=False)
    include_metadata: bool = Field(default=True)
    include_events: bool = Field(default=False, description="When true, include collected execution events for debugging.")

    @field_validator("user_input")
    @classmethod
    def validate_user_input(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("user_input must not be empty")
        return normalized

    @field_validator("requested_skill_id")
    @classmethod
    def normalize_requested_skill_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    def to_application_request(self) -> UnifiedExecutionRequest:
        from app.application.models import RetrievalOptions, SkillPolicy

        filters = self.filters.to_retrieval_filters() if self.filters else None
        return UnifiedExecutionRequest(
            task_type=TaskType(self.task_type),
            user_input=self.user_input,
            retrieval=RetrievalOptions(top_k=self.top_k, filters=filters),
            execution_policy=(self.execution_policy or ExecutionPolicyItem()).to_runtime_policy(),
            output_mode=OutputMode(self.output_mode),
            citation_policy=CitationPolicy(self.citation_policy),
            skill_policy=SkillPolicy(
                mode=SkillPolicyMode(self.skill_policy.mode),
                allowed_skill_ids=tuple(self.skill_policy.allowlist),
                denied_skill_ids=tuple(self.skill_policy.denied_skill_ids),
                require_public_listing=self.skill_policy.require_public_listing,
                allow_external_io=self.skill_policy.allow_external_io,
            ),
            requested_skill_id=self.requested_skill_id,
            requested_skill_arguments=dict(self.requested_skill_arguments),
            conversation_metadata=self.conversation_metadata,
            task_options=self.task_options,
            debug=self.debug,
            include_metadata=self.include_metadata,
            include_events=self.include_events,
        )


class ArtifactResponseItem(BaseModel):
    """Serializable artifact returned by unified execution."""

    artifact_id: str
    kind: str
    title: str | None = None
    description: str | None = None
    render_hint: str | None = None
    source_step_id: str | None = None
    content: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, object] = Field(default_factory=dict)
    citations: list[dict[str, Any]] = Field(default_factory=list)

    @classmethod
    def from_artifact(cls, artifact: BaseArtifact) -> "ArtifactResponseItem":
        content: dict[str, Any]
        if isinstance(artifact, TextArtifact):
            content = {"text": artifact.text}
        elif isinstance(artifact, MermaidArtifact):
            content = {"mermaid_code": artifact.mermaid_code}
        elif isinstance(artifact, SearchResultsArtifact):
            content = {
                "items": [
                    {
                        "chunk_id": item.chunk_id,
                        "doc_id": item.doc_id,
                        "source": item.source,
                        "source_type": item.source_type,
                        "title": item.title,
                        "snippet": item.snippet,
                        "score": item.score,
                        "page": item.page,
                        "anchor": item.anchor,
                    }
                    for item in artifact.items
                ],
                "total": artifact.total,
                "offset": artifact.offset,
                "limit": artifact.limit,
            }
        elif isinstance(artifact, StructuredJsonArtifact):
            content = {
                "data": artifact.data,
                "schema_name": artifact.schema_name,
                "validation_notes": list(artifact.validation_notes),
            }
        elif isinstance(artifact, SkillResultArtifact):
            content = {
                "skill_name": artifact.skill_name,
                "payload": artifact.payload,
                "summary_text": artifact.summary_text,
            }
        else:
            content = {}
        metadata = dict(artifact.metadata)
        grounded = metadata.get("grounded_answer")
        if grounded is not None:
            metadata["grounded_answer"] = GroundedAnswerItem.from_record(grounded).model_dump()
        compare = metadata.get("compare_result")
        if compare is not None:
            metadata["compare_result"] = CompareResultItem.from_record(compare).model_dump()
        if isinstance(artifact, StructuredJsonArtifact) and artifact.schema_name == "compare.v1":
            content["data"] = CompareResultItem.from_record(content["data"]).model_dump()
        # Extract citations from artifact.citations
        citations = list(artifact.citations) if artifact.citations else []
        return cls(
            artifact_id=artifact.artifact_id,
            kind=artifact.kind.value,
            title=artifact.title,
            description=artifact.description,
            render_hint=artifact.render_hint,
            source_step_id=artifact.source_step_id,
            content=content,
            metadata=metadata,
            citations=citations,
        )


class OutputBlockItem(BaseModel):
    """Deprecated compatibility projection for block-oriented clients."""

    kind: str
    content: str
    title: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class SkillInvocationItem(BaseModel):
    """Serializable skill invocation summary."""

    name: str
    ok: bool
    message: str | None = None
    output_preview: str | None = None


class ServiceIssueItem(BaseModel):
    """Serializable issue entry surfaced in metadata/execution summary."""

    code: str
    message: str
    severity: str = "warning"
    source: str | None = None


class RetrievalStatsItem(BaseModel):
    """Serializable retrieval stats snapshot."""

    retrieved_hits: int = 0
    grounded_hits: int = 0
    reranked_hits: int = 0
    returned_hits: int = 0


class ExecutionMetadataDeltaResponse(BaseModel):
    """Serializable metadata delta emitted inside execution events."""

    selected_runtime: str | None = None
    selected_profile_id: str | None = None
    selected_provider_kind: str | None = None
    selected_model_name: str | None = None
    execution_steps_executed: list[str] = Field(default_factory=list)
    artifact_kinds_returned: list[str] = Field(default_factory=list)
    artifact_count: int = 0
    partial_failure: bool | None = None
    warnings: list[str] = Field(default_factory=list)
    issues: list[ServiceIssueItem] = Field(default_factory=list)

    @classmethod
    def from_delta(cls, delta: ExecutionMetadataDelta) -> "ExecutionMetadataDeltaResponse":
        return cls(
            selected_runtime=delta.selected_runtime,
            selected_profile_id=delta.selected_profile_id,
            selected_provider_kind=delta.selected_provider_kind,
            selected_model_name=delta.selected_model_name,
            execution_steps_executed=list(delta.execution_steps_executed),
            artifact_kinds_returned=list(delta.artifact_kinds_returned),
            artifact_count=delta.artifact_count,
            partial_failure=delta.partial_failure,
            warnings=list(delta.warnings),
            issues=[
                ServiceIssueItem(
                    code=item.code,
                    message=item.message,
                    severity=item.severity,
                    source=item.source,
                )
                for item in delta.issues
            ],
        )


class ExecutionEventResponseItem(BaseModel):
    """Serializable execution event for debug and future streaming clients."""

    event_id: str
    run_id: str
    sequence: int
    kind: str
    step_id: str | None = None
    timestamp: str
    payload: dict[str, Any] = Field(default_factory=dict)
    metadata_delta: ExecutionMetadataDeltaResponse | None = None
    visibility: str = "public"
    debug_level: str = "normal"

    @classmethod
    def from_event(cls, event: ExecutionEvent) -> "ExecutionEventResponseItem":
        return cls(
            event_id=event.event_id,
            run_id=event.run_id,
            sequence=event.sequence,
            kind=event.kind.value,
            step_id=event.step_id,
            timestamp=event.timestamp,
            payload=_event_payload_to_dict(event),
            metadata_delta=None if event.metadata_delta is None else ExecutionMetadataDeltaResponse.from_delta(event.metadata_delta),
            visibility=event.visibility,
            debug_level=event.debug_level,
        )


class ClientEventResponseItem(BaseModel):
    """Serializable client-facing projected event."""

    event_id: str
    run_id: str
    sequence: int
    kind: str
    channel: str
    visibility: str
    timestamp: str
    payload: dict[str, Any] = Field(default_factory=dict)
    cursor: str | None = None

    @classmethod
    def from_client_event(cls, event: ClientEvent) -> "ClientEventResponseItem":
        return cls(
            event_id=event.event_id,
            run_id=event.run_id,
            sequence=event.sequence,
            kind=event.kind.value,
            channel=event.channel.value,
            visibility=event.visibility.value,
            timestamp=event.timestamp,
            payload=_client_event_payload_to_dict(event.payload),
            cursor=event.cursor,
        )


class RunFinalResponseSummaryItem(BaseModel):
    """Minimal summary of a run's final response."""

    task_type: str
    artifact_count: int
    primary_artifact_kind: str | None = None


class RunStatusResponse(BaseModel):
    """Serializable run status and summary."""

    run_id: str
    status: str
    created_at: str
    updated_at: str
    selected_runtime: str | None = None
    selected_profile_id: str | None = None
    selected_provider_kind: str | None = None
    event_count: int = 0
    cancellation_requested: bool = False
    has_final_response: bool = False
    final_response: RunFinalResponseSummaryItem | None = None
    error: dict[str, str] | None = None


class RunSummaryResponse(RunStatusResponse):
    """Alias schema for run summary queries."""


class RunEventListResponse(BaseModel):
    """Serializable transient replay response."""

    run_id: str
    status: str
    event_count: int
    items: list[ClientEventResponseItem] = Field(default_factory=list)


class CancelRunResponse(BaseModel):
    """Serializable response for a cancel request."""

    run_id: str
    status: str
    cancellation_requested: bool
    accepted: bool
    detail: str


class UnifiedExecutionMetadataResponse(BaseModel):
    """Metadata block for the unified execution API."""

    selected_runtime: str | None = None
    selected_profile_id: str | None = None
    selected_provider_kind: str | None = None
    selected_model_name: str | None = None
    runtime_capabilities_matched: list[str] = Field(default_factory=list)
    resolved_capabilities: list[str] = Field(default_factory=list)
    execution_steps_executed: list[str] = Field(default_factory=list)
    artifact_kinds_returned: list[str] = Field(default_factory=list)
    primary_artifact_kind: str | None = None
    artifact_count: int = 0
    search_result_count: int = 0
    skill_artifact_count: int = 0
    skill_invocations: list[SkillInvocationItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    issues: list[ServiceIssueItem] = Field(default_factory=list)
    insufficient_evidence: bool = False
    support_status: str | None = None
    refusal_reason: str | None = None
    partial_failure: bool = False
    fallback_used: bool = False
    selection_reason: str | None = None
    policy_applied: str | None = None
    filter_applied: bool = False
    retrieval_stats: RetrievalStatsItem | None = None
    workflow_trace: dict[str, Any] | None = None


class ExecutionSummaryResponse(BaseModel):
    """Execution summary block for the unified execution API."""

    selected_runtime: str | None = None
    selected_profile_id: str | None = None
    selected_provider_kind: str | None = None
    selected_model_name: str | None = None
    selected_capabilities: list[str] = Field(default_factory=list)
    fallback_used: bool = False
    selection_reason: str | None = None
    policy_applied: str | None = None
    execution_steps_executed: list[str] = Field(default_factory=list)
    artifact_kinds_returned: list[str] = Field(default_factory=list)
    primary_artifact_kind: str | None = None
    artifact_count: int = 0
    search_result_count: int = 0
    skill_artifact_count: int = 0
    skill_invocations: list[SkillInvocationItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    issues: list[ServiceIssueItem] = Field(default_factory=list)


class UnifiedExecutionResponseBody(BaseModel):
    """Response body for the unified frontend execution endpoint."""

    task_type: str
    run_id: str | None = None
    event_count: int = 0
    artifacts: list[ArtifactResponseItem]
    output_blocks: list[OutputBlockItem] = Field(default_factory=list)
    events: list[ExecutionEventResponseItem] | None = None
    citations: list[CitationItem]
    grounded_answer: GroundedAnswerItem | None = None
    compare_result: CompareResultItem | None = None
    metadata: UnifiedExecutionMetadataResponse
    execution_summary: ExecutionSummaryResponse

    @classmethod
    def from_result(cls, result: UnifiedExecutionResponse) -> "UnifiedExecutionResponseBody":
        retrieval_stats = None
        if result.metadata.retrieval_stats is not None:
            retrieval_stats = RetrievalStatsItem(
                retrieved_hits=result.metadata.retrieval_stats.retrieved_hits,
                grounded_hits=result.metadata.retrieval_stats.grounded_hits,
                reranked_hits=result.metadata.retrieval_stats.reranked_hits,
                returned_hits=result.metadata.retrieval_stats.returned_hits,
            )
        return cls(
            task_type=result.task_type.value,
            run_id=result.run_id,
            event_count=result.event_count,
            artifacts=[ArtifactResponseItem.from_artifact(artifact) for artifact in result.artifacts],
            output_blocks=[
                OutputBlockItem(
                    kind=str(block["kind"].value if hasattr(block["kind"], "value") else block["kind"]),
                    content=str(block["content"]),
                    title=block.get("title"),
                    metadata=dict(block.get("metadata") or {}),
                )
                for block in result.output_blocks
            ],
            events=None if not result.events else [ExecutionEventResponseItem.from_event(event) for event in result.events],
            citations=[CitationItem.from_record(item) for item in result.citations],
            grounded_answer=None if result.grounded_answer is None else GroundedAnswerItem.from_record(result.grounded_answer),
            compare_result=None if result.compare_result is None else CompareResultItem.from_record(result.compare_result),
            metadata=UnifiedExecutionMetadataResponse(
                selected_runtime=result.metadata.selected_runtime,
                selected_profile_id=result.metadata.selected_profile_id,
                selected_provider_kind=result.metadata.selected_provider_kind,
                selected_model_name=result.metadata.selected_model_name,
                runtime_capabilities_matched=list(result.metadata.runtime_capabilities_matched),
                resolved_capabilities=list(result.metadata.resolved_capabilities),
                execution_steps_executed=list(result.metadata.execution_steps_executed),
                artifact_kinds_returned=list(result.metadata.artifact_kinds_returned),
                primary_artifact_kind=result.metadata.primary_artifact_kind,
                artifact_count=result.metadata.artifact_count,
                search_result_count=result.metadata.search_result_count,
                skill_artifact_count=result.metadata.skill_artifact_count,
                skill_invocations=[
                    SkillInvocationItem(
                        name=item.name,
                        ok=item.ok,
                        message=item.message,
                        output_preview=item.output_preview,
                    )
                    for item in result.metadata.skill_invocations
                ],
                warnings=list(result.metadata.warnings),
                issues=[
                    ServiceIssueItem(
                        code=item.code,
                        message=item.message,
                        severity=item.severity,
                        source=item.source,
                    )
                    for item in result.metadata.issues
                ],
                insufficient_evidence=result.metadata.insufficient_evidence,
                support_status=result.metadata.support_status,
                refusal_reason=result.metadata.refusal_reason,
                partial_failure=result.metadata.partial_failure,
                fallback_used=result.metadata.fallback_used,
                selection_reason=result.metadata.selection_reason,
                policy_applied=result.metadata.policy_applied,
                filter_applied=result.metadata.filter_applied,
                retrieval_stats=retrieval_stats,
                workflow_trace=result.metadata.workflow_trace,
            ),
            execution_summary=ExecutionSummaryResponse(
                selected_runtime=result.execution_summary.selected_runtime,
                selected_profile_id=result.execution_summary.selected_profile_id,
                selected_provider_kind=result.execution_summary.selected_provider_kind,
                selected_model_name=result.execution_summary.selected_model_name,
                selected_capabilities=list(result.execution_summary.selected_capabilities),
                fallback_used=result.execution_summary.fallback_used,
                selection_reason=result.execution_summary.selection_reason,
                policy_applied=result.execution_summary.policy_applied,
                execution_steps_executed=list(result.execution_summary.execution_steps_executed),
                artifact_kinds_returned=list(result.execution_summary.artifact_kinds_returned),
                primary_artifact_kind=result.execution_summary.primary_artifact_kind,
                artifact_count=result.execution_summary.artifact_count,
                search_result_count=result.execution_summary.search_result_count,
                skill_artifact_count=result.execution_summary.skill_artifact_count,
                skill_invocations=[
                    SkillInvocationItem(
                        name=item.name,
                        ok=item.ok,
                        message=item.message,
                        output_preview=item.output_preview,
                    )
                    for item in result.execution_summary.skill_invocations
                ],
                warnings=list(result.execution_summary.warnings),
                issues=[
                    ServiceIssueItem(
                        code=item.code,
                        message=item.message,
                        severity=item.severity,
                        source=item.source,
                    )
                    for item in result.execution_summary.issues
                ],
            ),
        )


class SkillSchemaFieldResponse(BaseModel):
    """Frontend-safe summary of one skill schema field."""

    name: str
    field_type: str
    description: str
    required: bool = True
    enum_values: list[str] = Field(default_factory=list)
    items_type: str | None = None
    default: Any = None

    @classmethod
    def from_field(cls, field: SkillSchemaField) -> "SkillSchemaFieldResponse":
        return cls(
            name=field.name,
            field_type=field.field_type,
            description=field.description,
            required=field.required,
            enum_values=list(field.enum_values),
            items_type=field.items_type,
            default=field.default,
        )


class SkillSchemaSummaryResponse(BaseModel):
    """Frontend-safe summary of a skill input/output schema."""

    schema_name: str
    description: str
    fields: list[SkillSchemaFieldResponse] = Field(default_factory=list)

    @classmethod
    def from_schema(cls, schema: SkillInputSchema | SkillOutputSchema | None) -> "SkillSchemaSummaryResponse | None":
        if schema is None:
            return None
        return cls(
            schema_name=schema.schema_name,
            description=schema.description,
            fields=[SkillSchemaFieldResponse.from_field(field) for field in schema.fields],
        )


class SkillSummaryResponse(BaseModel):
    """Safe skill summary returned by the frontend skill catalog endpoint."""

    skill_id: str
    display_name: str
    description: str
    version: str
    capability_tags: list[str] = Field(default_factory=list)
    invocation_mode: str
    enabled: bool
    safe_for_public_listing: bool
    produces_artifact_kind: str | None = None

    @classmethod
    def from_entry(cls, entry: SkillCatalogEntry) -> "SkillSummaryResponse":
        return cls(
            skill_id=entry.skill_id,
            display_name=entry.display_name,
            description=entry.description,
            version=entry.version,
            capability_tags=list(entry.capability_tags),
            invocation_mode=entry.invocation_mode,
            enabled=entry.enabled,
            safe_for_public_listing=entry.safe_for_public_listing,
            produces_artifact_kind=entry.produces_artifact_kind,
        )


class SkillDetailResponse(BaseModel):
    """Safe skill detail returned by the frontend skill detail endpoint."""

    skill_id: str
    display_name: str
    description: str
    version: str
    capability_tags: list[str] = Field(default_factory=list)
    invocation_mode: str
    enabled: bool
    safe_for_public_listing: bool
    timeout_hint_ms: int | None = None
    produces_artifact_kind: str | None = None
    input_schema: SkillSchemaSummaryResponse | None = None
    output_schema: SkillSchemaSummaryResponse | None = None
    visibility_notes: list[str] = Field(default_factory=list)
    safety_notes: list[str] = Field(default_factory=list)

    @classmethod
    def from_detail(cls, detail: SkillCatalogDetail) -> "SkillDetailResponse":
        return cls(
            skill_id=detail.skill_id,
            display_name=detail.display_name,
            description=detail.description,
            version=detail.version,
            capability_tags=list(detail.capability_tags),
            invocation_mode=detail.invocation_mode,
            enabled=detail.enabled,
            safe_for_public_listing=detail.safe_for_public_listing,
            timeout_hint_ms=detail.timeout_hint_ms,
            produces_artifact_kind=detail.produces_artifact_kind,
            input_schema=SkillSchemaSummaryResponse.from_schema(detail.input_schema),
            output_schema=SkillSchemaSummaryResponse.from_schema(detail.output_schema),
            visibility_notes=list(detail.visibility_notes),
            safety_notes=list(detail.safety_notes),
        )


class SkillListResponse(BaseModel):
    """Response body for skill catalog listing."""

    items: list[SkillSummaryResponse]
    total: int

    @classmethod
    def from_entries(cls, entries: tuple[SkillCatalogEntry, ...] | list[SkillCatalogEntry]) -> "SkillListResponse":
        items = [SkillSummaryResponse.from_entry(entry) for entry in entries]
        return cls(items=items, total=len(items))


class SourceSkillSummaryResponse(BaseModel):
    """Declaration-only source skill shown in Settings > Sources."""

    id: str
    name: str
    kind: str
    version: str
    status: str
    description: str
    input_kinds: list[str] = Field(default_factory=list)
    output_type: str = ""
    source_media: str | None = None
    source_kind: str | None = None
    loader_name: str | None = None
    handler: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    providers: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    safety_notes: list[str] = Field(default_factory=list)
    enabled: bool = True
    origin: str = "builtin"

    @classmethod
    def from_info(cls, info: SkillInfo) -> "SourceSkillSummaryResponse":
        data = info.to_dict()
        return cls(**data)


class SourceSkillListResponse(BaseModel):
    """Response body for source skill catalog listing."""

    items: list[SourceSkillSummaryResponse]
    total: int

    @classmethod
    def from_infos(cls, infos: tuple[SkillInfo, ...] | list[SkillInfo]) -> "SourceSkillListResponse":
        items = [SourceSkillSummaryResponse.from_info(info) for info in infos]
        return cls(items=items, total=len(items))


class SourceSkillManifestRequest(BaseModel):
    """Request body for validating or registering a local source skill manifest."""

    manifest: dict[str, Any]


class SourceSkillValidationResponse(BaseModel):
    """Validation/register/enable/disable result for local source skills."""

    ok: bool
    skill_id: str | None = None
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    executable: bool = False
    reason: str = ""
    skill: SourceSkillSummaryResponse | None = None

    @classmethod
    def from_result(cls, result: SkillManifestValidationResult) -> "SourceSkillValidationResponse":
        return cls(
            ok=result.ok,
            skill_id=result.skill_id,
            errors=list(result.errors),
            warnings=list(result.warnings),
            executable=result.executable,
            reason=result.reason,
            skill=None if result.skill is None else SourceSkillSummaryResponse.from_info(result.skill),
        )


class RuntimeProfileSummaryResponse(BaseModel):
    """Frontend-safe runtime profile summary."""

    profile_id: str
    display_name: str
    provider_kind: str
    model_name: str
    tags: list[str] = Field(default_factory=list)
    enabled: bool = True
    capability_summary: list[str] = Field(default_factory=list)

    @classmethod
    def from_summary(cls, summary: RuntimeProfileSummary) -> "RuntimeProfileSummaryResponse":
        return cls(
            profile_id=summary.profile_id,
            display_name=summary.display_name,
            provider_kind=summary.provider_kind,
            model_name=summary.model_name,
            tags=list(summary.tags),
            enabled=summary.enabled,
            capability_summary=list(summary.capabilities),
        )


class RuntimeProfileListResponse(BaseModel):
    """Response body for runtime profile listing."""

    items: list[RuntimeProfileSummaryResponse]
    total: int

    @classmethod
    def from_summaries(cls, summaries: tuple[RuntimeProfileSummary, ...] | list[RuntimeProfileSummary]) -> "RuntimeProfileListResponse":
        items = [RuntimeProfileSummaryResponse.from_summary(item) for item in summaries]
        return cls(items=items, total=len(items))


class EffectiveRuntimeResponse(BaseModel):
    """Runtime profile that would be selected for a default frontend execution."""

    profile_id: str
    provider_kind: str
    model_name: str
    base_url: str | None = None
    source: str
    api_key_masked: bool = False


# ---------------------------------------------------------------------------
# Active Runtime Config (Phase 1: OpenAI-compatible)
# ---------------------------------------------------------------------------


class RuntimeConfigResponse(BaseModel):
    """Response body for the active runtime configuration.

    The api_key is masked — never returned as plaintext (Phase 1+).
    config_source tells you where the runtime credentials are actually coming from (Phase 3).
    """

    provider: str = Field(description="Provider kind, always 'openai_compatible' in Phase 1")
    base_url: str = Field(description="Base URL for the API endpoint")
    model: str = Field(description="Model name identifier")
    api_key_masked: bool = Field(description="True if an API key is configured (but the key itself is never returned)")
    enabled: bool = Field(description="True if the user-configured runtime is active")
    config_source: str = Field(
        description=(
            "Where the active runtime credentials are coming from: "
            "'active_config_env' = custom runtime with key in env; "
            "'active_config_disabled' = custom runtime disabled, using default; "
            "'env_override' = no active config but LLM_API_KEY is set in shell env; "
            "'default' = no config, using system defaults"
        )
    )
    effective_runtime: EffectiveRuntimeResponse | None = Field(
        default=None,
        description="Runtime profile currently selected by the execution resolver for default frontend runs.",
    )

    @classmethod
    def from_config(
        cls,
        config: "ActiveRuntimeConfig",
        config_source: str = "default",
        effective_runtime: EffectiveRuntimeResponse | None = None,
    ) -> "RuntimeConfigResponse":
        return cls(
            provider=config.provider,
            base_url=config.base_url,
            model=config.model,
            api_key_masked=config.api_key_source == "env",
            enabled=config.enabled,
            config_source=config_source,
            effective_runtime=effective_runtime,
        )


class RuntimeConfigUpdateRequest(BaseModel):
    """Request body for updating the active runtime configuration."""

    provider: str = Field(default="openai_compatible", description="Provider kind")
    base_url: str = Field(description="Base URL for the API endpoint")
    api_key: str | None = Field(
        default=None,
        description="API key to use for this process. Omit or leave blank to keep the current process key.",
    )
    model: str = Field(description="Model name identifier")
    enabled: bool = Field(default=True, description="Enable this configuration")

    @field_validator("base_url")
    @classmethod
    def base_url_must_be_valid(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            # Empty allowed here; cross-field check in model_validator below
            return v
        if not stripped.startswith(("http://", "https://")):
            raise ValueError("base_url must start with http:// or https://")
        return stripped

    @model_validator(mode="after")
    def base_url_required_when_enabled(self) -> "RuntimeConfigUpdateRequest":
        if self.enabled and not self.base_url.strip():
            raise ValueError("base_url cannot be empty when the configuration is enabled")
        return self

    @field_validator("model")
    @classmethod
    def model_must_be_non_empty(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("model cannot be empty")
        return stripped


class RuntimeConfigTestRequest(BaseModel):
    """Request body for testing the runtime connection without persisting."""

    provider: str = Field(default="openai_compatible", description="Provider kind")
    base_url: str = Field(description="Base URL for the API endpoint")
    api_key: str = Field(description="API key to test")
    model: str = Field(description="Model name identifier")


class RuntimeConfigTestResponse(BaseModel):
    """Response body for a runtime connection test."""

    success: bool = Field(description="True if the connection test passed")
    message: str = Field(description="Human-readable result message")
    error_kind: str | None = Field(
        default=None,
        description="Structured error kind if failed: 'invalid_url', 'auth_failure', 'model_not_found', 'timeout', 'network_error', 'unknown'",
    )


# ---------------------------------------------------------------------------
# Error
# ---------------------------------------------------------------------------

class ErrorResponse(BaseModel):
    """Structured error response returned by all endpoints on failure."""

    error: str = Field(description="Machine-readable error category")
    category: str | None = Field(
        default=None,
        description="Optional stable category alias for clients that prefer an explicit classification field.",
    )
    detail: str = Field(description="Human-readable description")
    request_id: str | None = Field(default=None, description="Optional request trace id")

    @classmethod
    def from_parts(
        cls,
        *,
        error: str,
        detail: str,
        request_id: str | None = None,
        category: str | None = None,
    ) -> "ErrorResponse":
        return cls(
            error=error,
            category=category or error,
            detail=detail,
            request_id=request_id,
        )


def _ensure_tuple(value: str | list[str] | None) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, list):
        return tuple(value)
    return (value,)


def _evidence_from_mapping(item: Mapping[str, object]) -> EvidenceObject:
    return EvidenceObject(
        doc_id=str(item.get("doc_id", "")),
        chunk_id=str(item.get("chunk_id", "")),
        source=str(item.get("source", "")),
        snippet=str(item.get("snippet", "")),
        page=item.get("page"),
        anchor=item.get("anchor"),
        score=item.get("score"),
        source_version=item.get("source_version"),
        content_hash=item.get("content_hash"),
        freshness=EvidenceFreshness(str(item.get("freshness") or "fresh")),
    )


def _compared_point_from_mapping(item: Mapping[str, object]) -> ComparedPoint:
    return ComparedPoint(
        statement=str(item.get("statement", "")),
        left_evidence=tuple(_evidence_from_mapping(evidence) for evidence in item.get("left_evidence", [])),
        right_evidence=tuple(_evidence_from_mapping(evidence) for evidence in item.get("right_evidence", [])),
        summary_note=None if item.get("summary_note") is None else str(item.get("summary_note")),
    )


def _resolve_grounded_answer(
    *,
    grounded,
    answer: str,
    citations,
    insufficient_evidence: bool,
    support_status,
    refusal_reason,
) -> GroundedAnswerItem:
    if grounded is not None:
        return GroundedAnswerItem.from_record(grounded)
    status = str(support_status or ("insufficient_evidence" if insufficient_evidence else "supported"))
    refusal = None if refusal_reason is None else str(refusal_reason)
    return GroundedAnswerItem(
        answer=answer,
        evidence=[EvidenceItem.from_record(item) for item in citations],
        support_status=status,
        refusal_reason=refusal,
    )


def _event_payload_to_dict(event: ExecutionEvent) -> dict[str, Any]:
    payload = event.payload
    if payload is None:
        return {}
    if isinstance(payload, RunStartedPayload):
        return {
            "request": {
                "task_type": payload.request.task_type,
                "user_input_preview": payload.request.user_input_preview,
                "output_mode": payload.request.output_mode,
                "top_k": payload.request.top_k,
                "citation_policy": payload.request.citation_policy,
                "skill_policy": payload.request.skill_policy,
            }
        }
    if isinstance(payload, PlanBuiltPayload):
        return {
            "step_count": payload.step_count,
            "step_ids": list(payload.step_ids),
            "step_kinds": list(payload.step_kinds),
            "requires_runtime": payload.requires_runtime,
        }
    if isinstance(payload, StepStartedPayload):
        return {
            "step_name": payload.step_name,
            "step_kind": payload.step_kind,
        }
    if isinstance(payload, StepCompletedPayload):
        return {
            "step_name": payload.step_name,
            "step_kind": payload.step_kind,
            "status": payload.status,
        }
    if isinstance(payload, ArtifactEmittedPayload):
        return {
            "artifact": ArtifactResponseItem.from_artifact(payload.artifact).model_dump(),
            "artifact_index": payload.artifact_index,
        }
    if isinstance(payload, WarningEmittedPayload):
        return {
            "message": payload.message,
            "code": payload.code,
            "source": payload.source,
        }
    if isinstance(payload, MetadataUpdatedPayload):
        return {"reason": payload.reason}
    if isinstance(payload, RunCompletedPayload):
        return {
            "artifact_count": payload.artifact_count,
            "primary_artifact_kind": payload.primary_artifact_kind,
            "partial_failure": payload.partial_failure,
        }
    if isinstance(payload, RunFailedPayload):
        return {
            "error": payload.error,
            "detail": payload.detail,
            "failed_step_id": payload.failed_step_id,
        }
    return {"kind": event.kind.value}


def _client_event_payload_to_dict(payload) -> dict[str, Any]:
    if isinstance(payload, ClientRunStartedPayload):
        return {
            "task_type": payload.task_type,
            "output_mode": payload.output_mode,
        }
    if isinstance(payload, ClientProgressPayload):
        return {
            "phase": payload.phase.value,
            "status": payload.status,
            "message": payload.message,
        }
    if isinstance(payload, ClientArtifactPayload):
        return {
            "artifact": ArtifactResponseItem.from_artifact(payload.artifact).model_dump(),
            "artifact_index": payload.artifact_index,
        }
    if isinstance(payload, ClientWarningPayload):
        return {"message": payload.message}
    if isinstance(payload, ClientHeartbeatPayload):
        return {"message": payload.message}
    if isinstance(payload, ClientCompletedPayload):
        return {
            "artifact_count": payload.artifact_count,
            "primary_artifact_kind": payload.primary_artifact_kind,
            "partial_failure": payload.partial_failure,
        }
    if isinstance(payload, ClientFailedPayload):
        return {
            "error": payload.error,
            "detail": payload.detail,
        }
    return {}
