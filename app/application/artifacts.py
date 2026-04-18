"""Application-facing execution artifact contract and artifact builders."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from itertools import count
from typing import Any

from app.rag.retrieval_models import SearchHitRecord
from app.services.service_models import ChatServiceResult, CompareServiceResult, SearchServiceResult, SummarizeServiceResult
from app.skills.models import SkillInvocationResult


class ArtifactKind(StrEnum):
    """Typed artifact kinds returned by unified execution."""

    TEXT = "text"
    MERMAID = "mermaid"
    SEARCH_RESULTS = "search_results"
    STRUCTURED_JSON = "structured_json"
    SKILL_RESULT = "skill_result"
    WARNING = "warning"


@dataclass(frozen=True)
class BaseArtifact:
    """Base application-facing artifact."""

    artifact_id: str
    kind: ArtifactKind
    title: str | None = None
    description: str | None = None
    render_hint: str | None = None
    source_step_id: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)
    citations: tuple[dict[str, object], ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class TextArtifact(BaseArtifact):
    """Plain text artifact."""

    text: str = ""


@dataclass(frozen=True)
class MermaidArtifact(BaseArtifact):
    """Mermaid code artifact."""

    mermaid_code: str = ""


@dataclass(frozen=True)
class SearchResultItemArtifact:
    """One search result item surfaced inside SearchResultsArtifact."""

    chunk_id: str
    doc_id: str
    source: str
    source_type: str
    title: str | None = None
    snippet: str = ""
    score: float | None = None
    page: int | None = None
    anchor: str | None = None


@dataclass(frozen=True)
class SearchResultsArtifact(BaseArtifact):
    """Search results artifact for front-end friendly result rendering."""

    items: tuple[SearchResultItemArtifact, ...] = ()
    total: int = 0
    offset: int = 0
    limit: int = 0


@dataclass(frozen=True)
class StructuredJsonArtifact(BaseArtifact):
    """Structured JSON-compatible artifact."""

    data: dict[str, Any] = field(default_factory=dict)
    schema_name: str | None = None
    validation_notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class SkillResultArtifact(BaseArtifact):
    """Skill result artifact."""

    skill_name: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    summary_text: str | None = None


class ArtifactBuilder:
    """Central builder that maps service/skill results into typed artifacts."""

    def __init__(self) -> None:
        self._counter = count(1)

    def build_chat_artifacts(self, result: ChatServiceResult) -> tuple[BaseArtifact, ...]:
        grounded_metadata = {}
        citations: tuple[dict[str, object], ...] = ()
        if result.grounded_answer is not None:
            grounded_metadata = {"grounded_answer": result.grounded_answer.to_api_dict()}
            # Extract citations from evidence for frontend consumption
            if result.grounded_answer.evidence:
                from app.api.schemas import EvidenceItem
                citations = tuple(
                    EvidenceItem.from_record(e).model_dump()
                    for e in result.grounded_answer.evidence
                )
        return (
            TextArtifact(
                artifact_id=self._next_id("text"),
                kind=ArtifactKind.TEXT,
                title="answer",
                render_hint="markdown",
                source_step_id="generate_answer",
                metadata=grounded_metadata,
                citations=citations,
                text=result.answer,
            ),
        )

    def build_summarize_artifacts(self, result: SummarizeServiceResult, *, output_mode: str) -> tuple[BaseArtifact, ...]:
        grounded_metadata = {}
        citations: tuple[dict[str, object], ...] = ()
        if result.grounded_answer is not None:
            grounded_metadata = {"grounded_answer": result.grounded_answer.to_api_dict()}
            # Extract citations from evidence for frontend consumption
            if result.grounded_answer.evidence:
                from app.api.schemas import EvidenceItem
                citations = tuple(
                    EvidenceItem.from_record(e).model_dump()
                    for e in result.grounded_answer.evidence
                )
        artifacts: list[BaseArtifact] = [
            TextArtifact(
                artifact_id=self._next_id("text"),
                kind=ArtifactKind.TEXT,
                title="summary",
                render_hint="markdown",
                source_step_id="generate_summary",
                metadata=grounded_metadata,
                citations=citations,
                text=result.summary,
            )
        ]
        if result.structured_output:
            artifacts.append(
                MermaidArtifact(
                    artifact_id=self._next_id("mermaid"),
                    kind=ArtifactKind.MERMAID,
                    title="summary_mermaid",
                    render_hint="mermaid",
                    source_step_id="format_output",
                    mermaid_code=result.structured_output,
                )
            )
        elif output_mode == "structured":
            artifacts.append(
                StructuredJsonArtifact(
                    artifact_id=self._next_id("structured"),
                    kind=ArtifactKind.STRUCTURED_JSON,
                    title="summary_structured",
                    render_hint="json",
                    source_step_id="format_output",
                    data={"summary": result.summary},
                    schema_name="summary.v1",
                )
            )
        return tuple(artifacts)

    def build_compare_artifacts(self, result: CompareServiceResult) -> tuple[BaseArtifact, ...]:
        compare_payload = result.compare_result.to_api_dict()

        # Extract citations from compare evidence for frontend consumption
        citations: list[dict[str, object]] = []
        seen_chunk_ids: set[str] = set()
        idx = 0

        from app.api.schemas import EvidenceItem
        for point_list_attr in ["common_points", "differences", "conflicts"]:
            point_list = getattr(result.compare_result, point_list_attr, [])
            for point in point_list:
                for evidence in list(point.left_evidence or []) + list(point.right_evidence or []):
                    if evidence.chunk_id not in seen_chunk_ids:
                        seen_chunk_ids.add(evidence.chunk_id)
                        citation_dict = EvidenceItem.from_record(evidence).model_dump()
                        citation_dict["inline_ref"] = f"[{idx + 1}]"
                        citation_dict["chunk_index"] = idx
                        citations.append(citation_dict)
                        idx += 1

        return (
            TextArtifact(
                artifact_id=self._next_id("text"),
                kind=ArtifactKind.TEXT,
                title="compare_summary",
                render_hint="markdown",
                source_step_id="format_compare_output",
                metadata={"compare_result": compare_payload},
                citations=tuple(citations),
                text=self._compare_summary_text(result),
            ),
            StructuredJsonArtifact(
                artifact_id=self._next_id("structured"),
                kind=ArtifactKind.STRUCTURED_JSON,
                title="compare_result",
                render_hint="json",
                source_step_id="format_compare_output",
                data=compare_payload,
                schema_name="compare.v1",
                citations=tuple(citations),
            ),
        )

    def build_search_artifacts(self, result: SearchServiceResult) -> tuple[BaseArtifact, ...]:
        items = tuple(self._build_search_item(hit) for hit in result.hits)
        return (
            SearchResultsArtifact(
                artifact_id=self._next_id("search"),
                kind=ArtifactKind.SEARCH_RESULTS,
                title="search_results",
                render_hint="list",
                source_step_id="format_search_output",
                items=items,
                total=len(items),
                offset=0,
                limit=result.top_k,
            ),
        )

    def build_skill_artifact(self, result: SkillInvocationResult, *, source_step_id: str | None = None) -> SkillResultArtifact:
        summary = str(
            result.output.get("text")
            or result.output.get("normalized_text")
            or result.summary_text
            or result.message
            or ""
        ).strip() or None
        return SkillResultArtifact(
            artifact_id=self._next_id("skill"),
            kind=ArtifactKind.SKILL_RESULT,
            title=f"skill:{result.skill_id}",
            render_hint="skill_result",
            source_step_id=source_step_id,
            skill_name=result.skill_id,
            payload=dict(result.output),
            summary_text=summary,
        )

    @staticmethod
    def _build_search_item(hit: SearchHitRecord) -> SearchResultItemArtifact:
        return SearchResultItemArtifact(
            chunk_id=hit.chunk.chunk_id,
            doc_id=hit.chunk.doc_id,
            source=hit.chunk.source,
            source_type=hit.chunk.source_type,
            title=hit.chunk.title or None,
            snippet=hit.chunk.text,
            score=hit.chunk.distance,
            page=hit.chunk.page,
            anchor=hit.chunk.anchor,
        )

    def _next_id(self, prefix: str) -> str:
        return f"{prefix}-{next(self._counter)}"

    @staticmethod
    def _compare_summary_text(result: CompareServiceResult) -> str:
        compare = result.compare_result
        if compare.support_status.value == "insufficient_evidence":
            return "Insufficient evidence to compare the requested documents."
        lines = [f"Comparison question: {compare.query}"]
        if compare.common_points:
            lines.append("Common points:")
            lines.extend(f"- {point.statement}" for point in compare.common_points)
        if compare.differences:
            lines.append("Differences:")
            lines.extend(f"- {point.statement}" for point in compare.differences)
        if compare.conflicts:
            lines.append("Conflicts:")
            lines.extend(f"- {point.statement}" for point in compare.conflicts)
        return "\n".join(lines)


class ArtifactMapper:
    """Compatibility mapper from artifacts to legacy outward-facing shapes."""

    @staticmethod
    def primary_text(artifacts: tuple[BaseArtifact, ...]) -> str:
        for artifact in artifacts:
            if isinstance(artifact, TextArtifact):
                return artifact.text
        return ""

    @staticmethod
    def first_mermaid(artifacts: tuple[BaseArtifact, ...]) -> MermaidArtifact | None:
        for artifact in artifacts:
            if isinstance(artifact, MermaidArtifact):
                return artifact
        return None

    @staticmethod
    def first_search_results(artifacts: tuple[BaseArtifact, ...]) -> SearchResultsArtifact | None:
        for artifact in artifacts:
            if isinstance(artifact, SearchResultsArtifact):
                return artifact
        return None

    @staticmethod
    def first_compare_artifact(artifacts: tuple[BaseArtifact, ...]) -> StructuredJsonArtifact | None:
        for artifact in artifacts:
            if isinstance(artifact, StructuredJsonArtifact) and artifact.schema_name == "compare.v1":
                return artifact
        return None
