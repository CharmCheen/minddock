"""Formal application-layer service result models."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.rag.retrieval_models import CitationRecord, ContextBlock, GroundedAnswer, GroundedCompareResult, RetrievedChunk, SearchResult
from app.rag.source_models import (
    DeleteSourceResult,
    IngestBatchResult,
    IngestSourceResult,
    SourceCatalogEntry,
    SourceDetail,
    SourceInspectResult,
)


@dataclass(frozen=True)
class SkillInvocation:
    """Structured record for one skill execution during a use case."""

    name: str
    ok: bool
    message: str | None = None
    output_preview: str | None = None


@dataclass(frozen=True)
class ServiceIssue:
    """Structured warning/issue emitted during a use case run."""

    code: str
    message: str
    severity: str = "warning"
    source: str | None = None


@dataclass(frozen=True)
class UseCaseTiming:
    """Lightweight timing summary for one use case execution."""

    total_ms: float | None = None
    retrieval_ms: float | None = None
    rerank_ms: float | None = None
    compress_ms: float | None = None
    generation_ms: float | None = None


@dataclass(frozen=True)
class SourceStats:
    """Compact source-processing stats for ingest-style use cases."""

    requested_sources: int = 0
    succeeded_sources: int = 0
    failed_sources: int = 0


@dataclass(frozen=True)
class RetrievalStats:
    """Compact retrieval-stage stats for retrieval-driven use cases."""

    retrieved_hits: int = 0
    grounded_hits: int = 0
    reranked_hits: int = 0
    returned_hits: int = 0


@dataclass(frozen=True)
class UseCaseMetadata:
    """Shared metadata attached to service-level results."""

    retrieved_count: int = 0
    mode: str | None = None
    output_format: str | None = None
    partial_failure: bool = False
    insufficient_evidence: bool = False
    support_status: str | None = None
    refusal_reason: str | None = None
    empty_result: bool = False
    warnings: tuple[str, ...] = ()
    issues: tuple[ServiceIssue, ...] = ()
    timing: UseCaseTiming = field(default_factory=UseCaseTiming)
    runtime_mode: str | None = None
    provider_mode: str | None = None
    selected_runtime: str | None = None
    selected_profile_id: str | None = None
    selected_provider_kind: str | None = None
    selected_model_name: str | None = None
    runtime_capabilities_matched: tuple[str, ...] = ()
    resolved_capabilities: tuple[str, ...] = ()
    execution_steps_executed: tuple[str, ...] = ()
    skill_invocations: tuple[SkillInvocation, ...] = ()
    artifact_kinds_returned: tuple[str, ...] = ()
    primary_artifact_kind: str | None = None
    artifact_count: int = 0
    search_result_count: int = 0
    skill_artifact_count: int = 0
    fallback_used: bool = False
    selection_reason: str | None = None
    policy_applied: str | None = None
    filter_applied: bool = False
    source_stats: SourceStats | None = None
    retrieval_stats: RetrievalStats | None = None
    debug_notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class SearchServiceResult:
    """Formal result returned by the search use case."""

    search_result: SearchResult
    metadata: UseCaseMetadata = field(default_factory=UseCaseMetadata)

    @property
    def query(self) -> str:
        return self.search_result.query

    @property
    def top_k(self) -> int:
        return self.search_result.top_k

    @property
    def hits(self):
        return self.search_result.hits

    def to_api_dict(self) -> dict[str, object]:
        return self.search_result.to_api_dict()


@dataclass(frozen=True)
class ChatServiceResult:
    """Formal result returned by the grounded chat use case."""

    answer: str
    citations: list[CitationRecord]
    grounded_answer: GroundedAnswer | None = None
    metadata: UseCaseMetadata = field(default_factory=UseCaseMetadata)
    context: ContextBlock | None = None

    def to_api_dict(self) -> dict[str, object]:
        grounded = self.grounded_answer
        return {
            "answer": self.answer,
            "evidence": [] if grounded is None else [item.to_api_dict() for item in grounded.evidence],
            "support_status": None if grounded is None else grounded.support_status.value,
            "refusal_reason": None if grounded is None or grounded.refusal_reason is None else grounded.refusal_reason.value,
            "citations": [item.to_api_dict() for item in self.citations],
            "retrieved_count": self.metadata.retrieved_count,
            "mode": self.metadata.mode or "grounded",
        }


@dataclass(frozen=True)
class SummarizeServiceResult:
    """Formal result returned by the grounded summarize use case."""

    summary: str
    citations: list[CitationRecord]
    grounded_answer: GroundedAnswer | None = None
    metadata: UseCaseMetadata = field(default_factory=UseCaseMetadata)
    structured_output: str | None = None
    context: ContextBlock | None = None

    def to_api_dict(self) -> dict[str, object]:
        grounded = self.grounded_answer
        return {
            "summary": self.summary,
            "evidence": [] if grounded is None else [item.to_api_dict() for item in grounded.evidence],
            "support_status": None if grounded is None else grounded.support_status.value,
            "refusal_reason": None if grounded is None or grounded.refusal_reason is None else grounded.refusal_reason.value,
            "citations": [item.to_api_dict() for item in self.citations],
            "retrieved_count": self.metadata.retrieved_count,
            "mode": self.metadata.mode or "basic",
            "output_format": self.metadata.output_format or "text",
            "structured_output": self.structured_output,
        }


@dataclass(frozen=True)
class CompareServiceResult:
    """Formal result returned by the grounded compare use case."""

    compare_result: GroundedCompareResult
    citations: list[CitationRecord]
    metadata: UseCaseMetadata = field(default_factory=UseCaseMetadata)
    context: ContextBlock | None = None

    def to_api_dict(self) -> dict[str, object]:
        return {
            **self.compare_result.to_api_dict(),
            "citations": [item.to_api_dict() for item in self.citations],
            "retrieved_count": self.metadata.retrieved_count,
            "mode": self.metadata.mode or "grounded_compare",
        }


@dataclass(frozen=True)
class IngestServiceResult:
    """Formal result returned by the ingest use case."""

    batch: IngestBatchResult
    metadata: UseCaseMetadata = field(default_factory=UseCaseMetadata)

    @property
    def documents(self) -> int:
        return self.batch.documents

    @property
    def chunks(self) -> int:
        return self.batch.chunks

    @property
    def ingested_sources(self) -> list[str]:
        return self.batch.ingested_sources

    @property
    def failed_sources(self):
        return self.batch.failed_sources

    def to_api_dict(self) -> dict[str, object]:
        payload = self.batch.to_api_dict()
        payload["partial_failure"] = self.metadata.partial_failure
        return payload


@dataclass(frozen=True)
class DocumentEvidenceGroup:
    """Grouped grounded evidence for one source document."""

    doc_id: str
    hits: list[RetrievedChunk]
    citation: CitationRecord
    context: ContextBlock


@dataclass(frozen=True)
class RetrievalPreparationResult:
    """Prepared retrieval state consumed by downstream use cases."""

    hits: list[RetrievedChunk]
    grounded_hits: list[RetrievedChunk]
    context: ContextBlock
    citations: list[CitationRecord]
    grouped_hits: list[DocumentEvidenceGroup] = field(default_factory=list)


@dataclass(frozen=True)
class CatalogServiceResult:
    """Formal result returned by source catalog listing."""

    entries: list[SourceCatalogEntry]
    metadata: UseCaseMetadata = field(default_factory=UseCaseMetadata)


@dataclass(frozen=True)
class SourceDetailServiceResult:
    """Formal result returned by source detail lookup."""

    found: bool
    detail: SourceDetail | None = None
    metadata: UseCaseMetadata = field(default_factory=UseCaseMetadata)
    include_admin_metadata: bool = False
    admin_metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class SourceInspectServiceResult:
    """Formal result returned by source inspect/chunk preview lookups."""

    found: bool
    inspect: SourceInspectResult | None = None
    metadata: UseCaseMetadata = field(default_factory=UseCaseMetadata)


@dataclass(frozen=True)
class DeleteSourceServiceResult:
    """Formal result returned by source deletion."""

    result: DeleteSourceResult
    metadata: UseCaseMetadata = field(default_factory=UseCaseMetadata)


@dataclass(frozen=True)
class ReingestSourceServiceResult:
    """Formal result returned by source reingest."""

    found: bool
    source_result: IngestSourceResult | None = None
    metadata: UseCaseMetadata = field(default_factory=UseCaseMetadata)
