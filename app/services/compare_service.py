"""Application service for grounded multi-document compare workflows."""

from __future__ import annotations

import json
import logging
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field, replace
from typing import Optional

from app.core.exceptions import ChatError
from app.llm.factory import get_generation_runtime
from app.llm.mock import INSUFFICIENT_EVIDENCE
from app.prompts import GROUNDED_COMPARE_JSON_PROFILE_ID, get_prompt_profile, prompt_profile_trace
from app.rag.retrieval_models import (
    ComparedPoint,
    EvidenceObject,
    GroundedCompareResult,
    RefusalReason,
    RetrievalFilters,
    RetrievedChunk,
    SupportStatus,
)
from app.rag.postprocess import Compressor, Reranker, get_compressor, get_reranker
from app.runtime import GenerationRuntime, RuntimeRequest
from app.services.grounded_generation import (
    PARTIAL_SUPPORT_DISTANCE,
    assess_grounding,
    build_citation,
    build_context,
    build_evidence,
    detect_model_refusal,
    select_grounded_hits,
)
from app.services.search_service import SearchService
from app.services.source_freshness import refresh_compare_result_freshness
from app.services.service_models import CompareServiceResult, RetrievalStats, ServiceIssue, UseCaseMetadata, UseCaseTiming
from app.services.workflow_trace import build_trace_warnings, final_source_summary, source_scope_trace
from ports.llm import LLMProvider

logger = logging.getLogger(__name__)


class _CompareRefusedError(ValueError):
    """Raised when the LLM explicitly refuses to compare due to insufficient evidence."""

_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "has",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "to",
    "with",
}
_NEGATION_WORDS = {"no", "not", "never", "without", "none"}
_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
_NUMBER_PATTERN = re.compile(r"\d+(?:\.\d+)?")
_OVERLAP_THRESHOLD = 0.2


@dataclass(frozen=True)
class _EvidenceGroup:
    key: str
    label: str
    hits: tuple[RetrievedChunk, ...]

    @property
    def best_hit(self) -> RetrievedChunk:
        return self.hits[0]

@dataclass
class _PreparedCompareState:
    """Intermediate state produced by the retrieval/preparation stage."""

    hits: list[RetrievedChunk]
    grounded_hits: list[RetrievedChunk]
    reranked_hits: list[RetrievedChunk]
    compressed_hits: list[RetrievedChunk]
    groups: list[_EvidenceGroup]
    retrieval_ms: float
    rerank_ms: float
    compress_ms: float
    source_warnings: list[str]


@dataclass
class _SourceRetrievalState:
    """Per-source retrieval and post-processing state."""

    hits: list[RetrievedChunk]
    grounded_hits: list[RetrievedChunk]
    reranked_hits: list[RetrievedChunk]
    compressed_hits: list[RetrievedChunk]
    retrieval_ms: float
    rerank_ms: float
    compress_ms: float


@dataclass
class CompareService:
    """Deterministic grounded compare workflow over retrieved evidence groups.

    CompareService now attempts an LLM-backed structured comparison first,
    and falls back to the original heuristic compare when the runtime is
    unavailable, returns unusable output, or produces invalid JSON.
    """

    search_service: SearchService = field(default_factory=SearchService)
    reranker: Reranker = field(default_factory=get_reranker)
    compressor: Compressor = field(default_factory=get_compressor)
    collection: object = field(default=None)
    runtime: GenerationRuntime = field(default_factory=get_generation_runtime)
    llm: LLMProvider | None = None

    def compare(
        self,
        *,
        question: str,
        top_k: int,
        filters: RetrievalFilters | None = None,
        precomputed_hits: Optional[list] = None,
    ) -> CompareServiceResult:
        """Run the compare workflow.

        Args:
            precomputed_hits: If provided, skip retrieval and use these hits directly.
        """
        try:
            started = time.perf_counter()
            logger.info("Compare started: question_preview=%s top_k=%d", question[:60], top_k)

            state = self._prepare_compare_state(
                question=question,
                top_k=top_k,
                filters=filters,
                precomputed_hits=precomputed_hits,
            )

            workflow_trace_base = {
                "operation": "compare",
                "requested_top_k": top_k,
                "internal_candidate_k": len(state.hits),
                **prompt_profile_trace(self._prompt_profile()),
                **source_scope_trace(filters),
                "cross_document_intent_detected": True,
                "initial_candidate_count": len(state.hits),
                "applied_rules": [],
            }

            if not state.grounded_hits:
                insufficient_trace = self._finalize_insufficient_trace(workflow_trace_base)
                for warning in state.source_warnings:
                    if warning not in insufficient_trace["trace_warnings"]:
                        insufficient_trace["trace_warnings"].append(warning)
                issues = self._build_source_limit_issues(state.source_warnings)
                return self._insufficient_result(
                    question=question,
                    hits=state.hits,
                    retrieval_ms=state.retrieval_ms,
                    started=started,
                    filters=filters,
                    workflow_trace=insufficient_trace,
                    extra_warnings=tuple(state.source_warnings),
                    extra_issues=tuple(issues),
                )

            if len(state.groups) < 2:
                trace_extra_warnings = list(state.source_warnings)
                trace_extra_warnings.append("insufficient_context")
                issues = self._build_source_limit_issues(state.source_warnings)
                return self._insufficient_result(
                    question=question,
                    hits=state.hits,
                    grounded_hits=state.grounded_hits,
                    returned_hits=state.compressed_hits,
                    retrieval_ms=state.retrieval_ms,
                    rerank_ms=state.rerank_ms,
                    compress_ms=state.compress_ms,
                    started=started,
                    filters=filters,
                    reason="insufficient_context",
                    workflow_trace=self._finalize_insufficient_trace(
                        workflow_trace_base,
                        after_rerank_count=len(state.reranked_hits),
                        final_candidate_count=len(state.compressed_hits),
                        extra_warnings=tuple(trace_extra_warnings),
                    ),
                    extra_warnings=tuple(state.source_warnings),
                    extra_issues=tuple(issues),
                )

            left_group, right_group = state.groups[:2]
            generation_started = time.perf_counter()
            try:
                common_points, differences, conflicts = self._compare_groups(
                    question=question,
                    left_group=left_group,
                    right_group=right_group,
                )
            except _CompareRefusedError:
                logger.info("Compare LLM refused due to insufficient evidence: question_preview=%s", question[:60])
                generation_ms = round((time.perf_counter() - generation_started) * 1000, 2)
                return self._insufficient_result(
                    question=question,
                    hits=state.hits,
                    grounded_hits=state.grounded_hits,
                    returned_hits=state.compressed_hits,
                    retrieval_ms=state.retrieval_ms,
                    rerank_ms=state.rerank_ms,
                    compress_ms=state.compress_ms,
                    generation_ms=generation_ms,
                    started=started,
                    filters=filters,
                    reason="model_refused",
                    workflow_trace=self._finalize_insufficient_trace(
                        workflow_trace_base,
                        after_rerank_count=len(state.reranked_hits),
                        final_candidate_count=len(state.compressed_hits),
                        extra_warnings=("Model refused to compare due to insufficient evidence.",),
                    ),
                    extra_warnings=tuple(state.source_warnings) + ("Model refused to compare due to insufficient evidence.",),
                )
            generation_ms = round((time.perf_counter() - generation_started) * 1000, 2)
            compare_result = self._build_compare_result(
                question=question,
                hits=state.hits,
                left_group=left_group,
                right_group=right_group,
                common_points=common_points,
                differences=differences,
                conflicts=conflicts,
            )
            compare_result = refresh_compare_result_freshness(compare_result, collection=self.collection)
            citations = self._collect_citations(compare_result)

            trace_warnings = build_trace_warnings(citations=citations)
            for warning in state.source_warnings:
                if warning not in trace_warnings:
                    trace_warnings.append(warning)

            workflow_trace = {
                **workflow_trace_base,
                "after_rerank_count": len(state.reranked_hits),
                "final_candidate_count": len(state.compressed_hits),
                "final_citation_count": len(citations),
                "final_evidence_count": len(citations),
                "applied_rules": [],
                "final_sources": final_source_summary(citations),
                "trace_warnings": trace_warnings,
            }
            logger.info(
                "Compare completed: question_preview=%s groups=%d returned=%d",
                question[:60],
                len(state.groups),
                len(state.compressed_hits),
            )

            metadata_warnings = list(state.source_warnings)
            metadata_issues: list[ServiceIssue] = []
            for warning in state.source_warnings:
                metadata_issues.append(
                    ServiceIssue(
                        code="compare_source_limit",
                        message=warning,
                        severity="warning",
                    )
                )

            return CompareServiceResult(
                compare_result=compare_result,
                citations=citations,
                metadata=UseCaseMetadata(
                    retrieved_count=len(state.compressed_hits),
                    mode="grounded_compare",
                    insufficient_evidence=compare_result.support_status == SupportStatus.INSUFFICIENT_EVIDENCE,
                    support_status=compare_result.support_status.value,
                    refusal_reason=None if compare_result.refusal_reason is None else compare_result.refusal_reason.value,
                    warnings=tuple(metadata_warnings),
                    issues=tuple(metadata_issues),
                    timing=UseCaseTiming(
                        total_ms=round((time.perf_counter() - started) * 1000, 2),
                        retrieval_ms=state.retrieval_ms,
                        rerank_ms=state.rerank_ms,
                        compress_ms=state.compress_ms,
                        generation_ms=generation_ms,
                    ),
                    runtime_mode=getattr(self.runtime, "runtime_name", type(self.runtime).__name__),
                    provider_mode=type(self.llm).__name__ if self.llm is not None else getattr(self.runtime, "provider_name", None),
                    filter_applied=filters is not None,
                    retrieval_stats=RetrievalStats(
                        retrieved_hits=len(state.hits),
                        grounded_hits=len(state.grounded_hits),
                        reranked_hits=len(state.reranked_hits),
                        returned_hits=len(state.compressed_hits),
                    ),
                    workflow_trace=workflow_trace,
                ),
                context=build_context(state.compressed_hits),
            )
        except Exception as exc:
            logger.exception("Compare failed: question_preview=%s", question[:60])
            raise ChatError(detail=f"Compare generation failed: {exc}") from exc
    def _prepare_compare_state(
        self,
        question: str,
        top_k: int,
        filters: RetrievalFilters | None,
        precomputed_hits: list[RetrievedChunk] | None,
    ) -> _PreparedCompareState:
        selected_sources = filters.sources if filters is not None else ()

        if precomputed_hits is not None:
            hits = precomputed_hits
            retrieval_ms = 0.0
            source_warnings: list[str] = []
            grounded_hits = select_grounded_hits(hits).hits
            rerank_started = time.perf_counter()
            reranked_hits = self.reranker.rerank(query=question, hits=grounded_hits)
            rerank_ms = round((time.perf_counter() - rerank_started) * 1000, 2)
            compress_started = time.perf_counter()
            compressed_hits = self.compressor.compress(query=question, hits=reranked_hits)
            compress_ms = round((time.perf_counter() - compress_started) * 1000, 2)
            groups = self._group_hits(compressed_hits)
            return _PreparedCompareState(
                hits=hits,
                grounded_hits=grounded_hits,
                reranked_hits=reranked_hits,
                compressed_hits=compressed_hits,
                groups=groups,
                retrieval_ms=retrieval_ms,
                rerank_ms=rerank_ms,
                compress_ms=compress_ms,
                source_warnings=source_warnings,
            )

        if len(selected_sources) >= 2:
            source_warnings = []
            if len(selected_sources) > 2:
                source_warnings.append(
                    "Compare currently supports two sources; additional sources were ignored."
                )
            source_a, source_b = selected_sources[0], selected_sources[1]
            left_state = self._retrieve_process_source(question, top_k, filters, source_a)
            right_state = self._retrieve_process_source(question, top_k, filters, source_b)

            hits = left_state.hits + right_state.hits
            grounded_hits = left_state.grounded_hits + right_state.grounded_hits
            reranked_hits = left_state.reranked_hits + right_state.reranked_hits
            compressed_hits = left_state.compressed_hits + right_state.compressed_hits
            retrieval_ms = round(left_state.retrieval_ms + right_state.retrieval_ms, 2)
            rerank_ms = round(left_state.rerank_ms + right_state.rerank_ms, 2)
            compress_ms = round(left_state.compress_ms + right_state.compress_ms, 2)

            groups: list[_EvidenceGroup] = []
            if left_state.compressed_hits:
                groups.append(
                    _EvidenceGroup(
                        key=source_a,
                        label=self._group_label(left_state.compressed_hits[0]),
                        hits=tuple(sorted(left_state.compressed_hits, key=self._hit_sort_key)),
                    )
                )
            if right_state.compressed_hits:
                groups.append(
                    _EvidenceGroup(
                        key=source_b,
                        label=self._group_label(right_state.compressed_hits[0]),
                        hits=tuple(sorted(right_state.compressed_hits, key=self._hit_sort_key)),
                    )
                )
            return _PreparedCompareState(
                hits=hits,
                grounded_hits=grounded_hits,
                reranked_hits=reranked_hits,
                compressed_hits=compressed_hits,
                groups=groups,
                retrieval_ms=retrieval_ms,
                rerank_ms=rerank_ms,
                compress_ms=compress_ms,
                source_warnings=source_warnings,
            )

        # Standard single-retrieval path
        retrieval_started = time.perf_counter()
        hits = self.search_service.retrieve(query=question, top_k=top_k, filters=filters)
        retrieval_ms = round((time.perf_counter() - retrieval_started) * 1000, 2)
        source_warnings = []
        grounded_hits = select_grounded_hits(hits).hits
        rerank_started = time.perf_counter()
        reranked_hits = self.reranker.rerank(query=question, hits=grounded_hits)
        rerank_ms = round((time.perf_counter() - rerank_started) * 1000, 2)
        compress_started = time.perf_counter()
        compressed_hits = self.compressor.compress(query=question, hits=reranked_hits)
        compress_ms = round((time.perf_counter() - compress_started) * 1000, 2)
        groups = self._group_hits(compressed_hits)
        return _PreparedCompareState(
            hits=hits,
            grounded_hits=grounded_hits,
            reranked_hits=reranked_hits,
            compressed_hits=compressed_hits,
            groups=groups,
            retrieval_ms=retrieval_ms,
            rerank_ms=rerank_ms,
            compress_ms=compress_ms,
            source_warnings=source_warnings,
        )

    def _retrieve_process_source(
        self,
        question: str,
        top_k: int,
        filters: RetrievalFilters,
        source: str,
    ) -> _SourceRetrievalState:
        source_filters = replace(filters, sources=(source,))
        retrieval_started = time.perf_counter()
        hits = self.search_service.retrieve(query=question, top_k=top_k, filters=source_filters)
        retrieval_ms = round((time.perf_counter() - retrieval_started) * 1000, 2)
        grounded_hits = select_grounded_hits(hits).hits
        rerank_started = time.perf_counter()
        reranked_hits = self.reranker.rerank(query=question, hits=grounded_hits)
        rerank_ms = round((time.perf_counter() - rerank_started) * 1000, 2)
        compress_started = time.perf_counter()
        compressed_hits = self.compressor.compress(query=question, hits=reranked_hits)
        compress_ms = round((time.perf_counter() - compress_started) * 1000, 2)
        return _SourceRetrievalState(
            hits=hits,
            grounded_hits=grounded_hits,
            reranked_hits=reranked_hits,
            compressed_hits=compressed_hits,
            retrieval_ms=retrieval_ms,
            rerank_ms=rerank_ms,
            compress_ms=compress_ms,
        )

    def _insufficient_result(
        self,
        *,
        question: str,
        hits: list[RetrievedChunk],
        retrieval_ms: float,
        started: float,
        filters: RetrievalFilters | None,
        grounded_hits: list[RetrievedChunk] | None = None,
        returned_hits: list[RetrievedChunk] | None = None,
        rerank_ms: float | None = None,
        compress_ms: float | None = None,
        generation_ms: float | None = None,
        reason: str | None = None,
        workflow_trace: dict[str, object] | None = None,
        extra_warnings: tuple[str, ...] = (),
        extra_issues: tuple[ServiceIssue, ...] = (),
    ) -> CompareServiceResult:
        compare_result = GroundedCompareResult(
            query=question,
            support_status=SupportStatus.INSUFFICIENT_EVIDENCE,
            refusal_reason=assess_grounding(retrieved_hits=hits, evidence=[]).refusal_reason if reason is None else None,
        )
        if reason == "insufficient_context":
            compare_result = GroundedCompareResult(
                query=question,
                support_status=SupportStatus.INSUFFICIENT_EVIDENCE,
                refusal_reason=RefusalReason.INSUFFICIENT_CONTEXT,
            )
        elif reason == "model_refused":
            compare_result = GroundedCompareResult(
                query=question,
                support_status=SupportStatus.INSUFFICIENT_EVIDENCE,
                refusal_reason=RefusalReason.MODEL_REFUSED,
            )
        refusal_reason = compare_result.refusal_reason
        return CompareServiceResult(
            compare_result=GroundedCompareResult(
                query=question,
                support_status=SupportStatus.INSUFFICIENT_EVIDENCE,
                refusal_reason=refusal_reason,
            ),
            citations=[],
            metadata=UseCaseMetadata(
                retrieved_count=0 if not returned_hits else len(returned_hits),
                mode="grounded_compare",
                insufficient_evidence=True,
                support_status=SupportStatus.INSUFFICIENT_EVIDENCE.value,
                refusal_reason=None if refusal_reason is None else refusal_reason.value,
                empty_result=not hits,
                warnings=self._merge_insufficient_warnings(extra_warnings),
                issues=self._merge_insufficient_issues(extra_issues),
                timing=UseCaseTiming(
                    total_ms=round((time.perf_counter() - started) * 1000, 2),
                    retrieval_ms=retrieval_ms,
                    rerank_ms=rerank_ms,
                    compress_ms=compress_ms,
                    generation_ms=generation_ms,
                ),
                filter_applied=filters is not None,
                retrieval_stats=RetrievalStats(
                    retrieved_hits=len(hits),
                    grounded_hits=0 if grounded_hits is None else len(grounded_hits),
                    returned_hits=0 if returned_hits is None else len(returned_hits),
                ),
                workflow_trace=workflow_trace,
            ),
            context=None if not returned_hits else build_context(returned_hits),
        )

    @staticmethod
    def _build_source_limit_issues(source_warnings: list[str]) -> list[ServiceIssue]:
        issues: list[ServiceIssue] = []
        for warning in source_warnings:
            issues.append(
                ServiceIssue(
                    code="compare_source_limit",
                    message=warning,
                    severity="warning",
                )
            )
        return issues

    @staticmethod
    def _merge_insufficient_warnings(extra_warnings: tuple[str, ...]) -> tuple[str, ...]:
        merged = list(extra_warnings)
        base = "Insufficient grounded evidence for compare response."
        if base not in merged:
            merged.append(base)
        return tuple(merged)

    @staticmethod
    def _merge_insufficient_issues(extra_issues: tuple[ServiceIssue, ...]) -> tuple[ServiceIssue, ...]:
        base = ServiceIssue(
            code="insufficient_evidence",
            message="Insufficient grounded evidence for compare response.",
            severity="info",
        )
        return (base,) + extra_issues

    @staticmethod
    def _clamp_confidence(value: object) -> float | None:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return max(0.0, min(1.0, float(value)))
        if isinstance(value, str):
            try:
                parsed = float(value.strip())
                return max(0.0, min(1.0, parsed))
            except (TypeError, ValueError):
                return None
        return None

    @staticmethod
    def _normalize_taxonomy(value: object) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            return None
        lowered = value.strip().lower()
        allowed = {"definition", "method", "assumption", "evidence", "conclusion", "scope", "other"}
        if lowered in allowed:
            return lowered
        return "other"

    @staticmethod
    def _compute_evidence_coverage(
        left_evidence: tuple[EvidenceObject, ...],
        right_evidence: tuple[EvidenceObject, ...],
    ) -> dict[str, object]:
        left_count = len(left_evidence)
        right_count = len(right_evidence)
        if left_count == 0 and right_count == 0:
            coverage_label = "unknown"
        elif left_count == 0 or right_count == 0:
            coverage_label = "single_sided"
        elif left_count == right_count:
            coverage_label = "balanced"
        elif left_count > right_count:
            coverage_label = "left_heavy"
        else:
            coverage_label = "right_heavy"
        return {
            "left_count": left_count,
            "right_count": right_count,
            "balanced": left_count == right_count and left_count > 0,
            "coverage_label": coverage_label,
        }

    def _finalize_insufficient_trace(
        self,
        trace: dict[str, object],
        *,
        after_rerank_count: int | None = None,
        final_candidate_count: int = 0,
        extra_warnings: tuple[str, ...] = (),
    ) -> dict[str, object]:
        if after_rerank_count is not None:
            trace["after_rerank_count"] = after_rerank_count
        trace["final_candidate_count"] = final_candidate_count
        trace["final_citation_count"] = 0
        trace["final_evidence_count"] = 0
        trace["final_sources"] = []
        warnings = build_trace_warnings(citations=[])
        for warning in extra_warnings:
            if warning not in warnings:
                warnings.append(warning)
        trace["trace_warnings"] = warnings
        return trace

    def _group_hits(self, hits: list[RetrievedChunk]) -> list[_EvidenceGroup]:
        grouped: dict[str, list[RetrievedChunk]] = defaultdict(list)
        for hit in hits:
            key = hit.doc_id or hit.source
            grouped[key].append(hit)
        groups = [
            _EvidenceGroup(
                key=key,
                label=self._group_label(doc_hits[0]),
                hits=tuple(sorted(doc_hits, key=self._hit_sort_key)),
            )
            for key, doc_hits in grouped.items()
            if doc_hits
        ]
        return sorted(groups, key=lambda item: self._hit_sort_key(item.best_hit))

    def _compare_groups(
        self,
        *,
        question: str,
        left_group: _EvidenceGroup,
        right_group: _EvidenceGroup,
    ) -> tuple[tuple[ComparedPoint, ...], tuple[ComparedPoint, ...], tuple[ComparedPoint, ...]]:
        """Try LLM-backed structured compare; fall back to heuristic on any failure."""
        try:
            return self._generate_compare_result_with_llm(
                question=question,
                left_group=left_group,
                right_group=right_group,
            )
        except _CompareRefusedError:
            raise
        except Exception:
            logger.info("Compare LLM path failed; falling back to heuristic compare.")
            return self._compare_groups_heuristic(
                question=question,
                left_group=left_group,
                right_group=right_group,
            )

    def _generate_compare_result_with_llm(
        self,
        *,
        question: str,
        left_group: _EvidenceGroup,
        right_group: _EvidenceGroup,
    ) -> tuple[tuple[ComparedPoint, ...], tuple[ComparedPoint, ...], tuple[ComparedPoint, ...]]:
        prompt = self._build_compare_prompt(
            question=question,
            left_group=left_group,
            right_group=right_group,
        )
        fallback_evidence = [
            {
                "chunk_id": hit.chunk_id,
                "source": hit.source or hit.doc_id,
                "text": hit.text,
            }
            for hit in (*left_group.hits, *right_group.hits)
        ]
        runtime_response = self.runtime.generate(
            RuntimeRequest(
                prompt=prompt,
                inputs={},
                fallback_query=question,
                fallback_evidence=fallback_evidence,
                llm_override=self.llm,
            )
        )
        text = runtime_response.text.strip()
        if not text:
            raise ValueError("Runtime returned empty text.")
        refusal = detect_model_refusal(text)
        if refusal:
            logger.info("Compare LLM returned refusal text: pattern=%s", refusal)
            raise _CompareRefusedError(f"LLM refused to compare: {refusal}")
        return self._parse_compare_llm_output(
            text=text,
            left_group=left_group,
            right_group=right_group,
        )

    def _build_compare_prompt(
        self,
        *,
        question: str,
        left_group: _EvidenceGroup,
        right_group: _EvidenceGroup,
    ) -> str:
        return self._prompt_profile().builder(
            question=question,
            left_label=left_group.label,
            left_evidence=tuple(hit.text for hit in left_group.hits),
            right_label=right_group.label,
            right_evidence=tuple(hit.text for hit in right_group.hits),
        )

    def _prompt_profile(self):
        return get_prompt_profile(GROUNDED_COMPARE_JSON_PROFILE_ID)

    def _extract_json_text(self, text: str) -> str:
        """Extract JSON from raw text, handling markdown fences and plain objects."""
        text = text.strip()
        # Try raw JSON first
        try:
            json.loads(text)
            return text
        except Exception:
            pass

        # Try ```json fence
        match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
        if match:
            candidate = match.group(1).strip()
            try:
                json.loads(candidate)
                return candidate
            except Exception:
                pass

        # Try plain ``` fence (take first fenced block)
        match = re.search(r"```\s*(.*?)\s*```", text, re.DOTALL)
        if match:
            candidate = match.group(1).strip()
            try:
                json.loads(candidate)
                return candidate
            except Exception:
                pass

        # Try first '{' to last '}'
        brace_start = text.find("{")
        brace_end = text.rfind("}")
        if brace_start != -1 and brace_end != -1 and brace_end > brace_start:
            candidate = text[brace_start : brace_end + 1]
            try:
                json.loads(candidate)
                return candidate
            except Exception:
                pass

        return text

    def _parse_compare_llm_output(
        self,
        *,
        text: str,
        left_group: _EvidenceGroup,
        right_group: _EvidenceGroup,
    ) -> tuple[tuple[ComparedPoint, ...], tuple[ComparedPoint, ...], tuple[ComparedPoint, ...]]:
        extracted = self._extract_json_text(text)
        parsed = json.loads(extracted)
        if not isinstance(parsed, dict):
            raise ValueError("Parsed JSON is not an object.")

        for key in ("common_points", "differences", "conflicts"):
            if key not in parsed:
                raise ValueError(f"Missing required key: {key}")
            if not isinstance(parsed[key], list):
                raise ValueError(f"Key '{key}' must be a list.")

        left_map = self._build_evidence_map(left_group, prefix="L")
        right_map = self._build_evidence_map(right_group, prefix="R")

        common_points = self._build_compared_points(
            parsed.get("common_points", []), left_map, right_map, left_group, right_group
        )
        differences = self._build_compared_points(
            parsed.get("differences", []), left_map, right_map, left_group, right_group
        )
        conflicts = self._build_compared_points(
            parsed.get("conflicts", []), left_map, right_map, left_group, right_group
        )

        if not common_points and not differences and not conflicts:
            raise ValueError("LLM returned empty compare result.")

        return common_points, differences, conflicts

    def _build_evidence_map(self, group: _EvidenceGroup, prefix: str) -> dict[str, RetrievedChunk]:
        return {f"{prefix}{index}": hit for index, hit in enumerate(group.hits, start=1)}

    def _build_compared_points(
        self,
        items: list[object],
        left_map: dict[str, RetrievedChunk],
        right_map: dict[str, RetrievedChunk],
        left_group: _EvidenceGroup,
        right_group: _EvidenceGroup,
    ) -> tuple[ComparedPoint, ...]:
        points: list[ComparedPoint] = []
        for item in items:
            if not isinstance(item, dict):
                continue

            # statement must be a non-empty string
            statement = item.get("statement")
            if not isinstance(statement, str) or not statement.strip():
                continue

            # summary_note must be string/None/missing
            summary_note = item.get("summary_note")
            if summary_note is not None and not isinstance(summary_note, str):
                summary_note = None
            if isinstance(summary_note, str):
                summary_note = summary_note.strip() or None

            # evidence_ids must be list or tuple; reject strings and other types
            left_ids = item.get("left_evidence_ids")
            right_ids = item.get("right_evidence_ids")
            if left_ids is not None and not isinstance(left_ids, (list, tuple)):
                left_ids = []
            if right_ids is not None and not isinstance(right_ids, (list, tuple)):
                right_ids = []

            left_evidence = self._resolve_evidence(left_ids, left_map)
            if not left_evidence:
                left_evidence = (build_evidence(left_group.best_hit),)

            right_evidence = self._resolve_evidence(right_ids, right_map)
            if not right_evidence:
                right_evidence = (build_evidence(right_group.best_hit),)

            # A grounded compare point must have evidence on both sides
            if not left_evidence or not right_evidence:
                continue

            confidence = self._clamp_confidence(item.get("confidence"))
            taxonomy = self._normalize_taxonomy(item.get("taxonomy"))
            evidence_coverage = self._compute_evidence_coverage(left_evidence, right_evidence)

            points.append(
                ComparedPoint(
                    statement=statement,
                    left_evidence=left_evidence,
                    right_evidence=right_evidence,
                    summary_note=summary_note,
                    confidence=confidence,
                    taxonomy=taxonomy,
                    evidence_coverage=evidence_coverage,
                )
            )
        return tuple(points)

    def _resolve_evidence(
        self,
        ids: list[object] | tuple[object, ...] | None,
        evidence_map: dict[str, RetrievedChunk],
    ) -> tuple[EvidenceObject, ...]:
        if ids is None:
            return ()
        results: list[EvidenceObject] = []
        for eid in ids:
            if isinstance(eid, str) and eid in evidence_map:
                results.append(build_evidence(evidence_map[eid]))
        return tuple(results)

    def _compare_groups_heuristic(
        self,
        *,
        question: str,
        left_group: _EvidenceGroup,
        right_group: _EvidenceGroup,
    ) -> tuple[tuple[ComparedPoint, ...], tuple[ComparedPoint, ...], tuple[ComparedPoint, ...]]:
        left_hit = left_group.best_hit
        right_hit = right_group.best_hit
        left_evidence = (build_evidence(left_hit),)
        right_evidence = (build_evidence(right_hit),)

        common_points = (
            ComparedPoint(
                statement=f"Both sources contain evidence relevant to: {question}",
                left_evidence=left_evidence,
                right_evidence=right_evidence,
                summary_note=f"{left_group.label} and {right_group.label} both discuss the requested topic.",
                confidence=None,
                taxonomy=None,
                evidence_coverage=self._compute_evidence_coverage(left_evidence, right_evidence),
            ),
        )

        differences: tuple[ComparedPoint, ...] = ()
        if self._normalized_text(left_hit) != self._normalized_text(right_hit):
            differences = (
                ComparedPoint(
                    statement=f"{left_group.label} and {right_group.label} emphasize different details.",
                    left_evidence=left_evidence,
                    right_evidence=right_evidence,
                    summary_note=(
                        f"Left focus: {self._preview(left_hit.text)} | "
                        f"Right focus: {self._preview(right_hit.text)}"
                    ),
                    confidence=None,
                    taxonomy=None,
                    evidence_coverage=self._compute_evidence_coverage(left_evidence, right_evidence),
                ),
            )

        conflicts: tuple[ComparedPoint, ...] = ()
        if self._looks_conflicting(left_hit.text, right_hit.text):
            conflicts = (
                ComparedPoint(
                    statement=f"{left_group.label} and {right_group.label} appear to conflict on the requested topic.",
                    left_evidence=left_evidence,
                    right_evidence=right_evidence,
                    summary_note="The paired evidence shares topic terms but differs in numbers or polarity.",
                    confidence=None,
                    taxonomy=None,
                    evidence_coverage=self._compute_evidence_coverage(left_evidence, right_evidence),
                ),
            )
        return common_points, differences, conflicts

    def _build_compare_result(
        self,
        *,
        question: str,
        hits: list[RetrievedChunk],
        left_group: _EvidenceGroup,
        right_group: _EvidenceGroup,
        common_points: tuple[ComparedPoint, ...],
        differences: tuple[ComparedPoint, ...],
        conflicts: tuple[ComparedPoint, ...],
    ) -> GroundedCompareResult:
        evidence = [
            item
            for point in (*common_points, *differences, *conflicts)
            for item in (*point.left_evidence, *point.right_evidence)
        ]
        grounding = assess_grounding(retrieved_hits=hits, evidence=evidence)
        support_status = grounding.support_status
        refusal_reason = grounding.refusal_reason
        if conflicts:
            support_status = SupportStatus.CONFLICTING_EVIDENCE
            refusal_reason = None
        elif differences and not self._has_strong_group(left_group) or not self._has_strong_group(right_group):
            support_status = SupportStatus.PARTIALLY_SUPPORTED
            refusal_reason = None
        if not common_points and not differences and not conflicts:
            support_status = SupportStatus.INSUFFICIENT_EVIDENCE
        return GroundedCompareResult(
            query=question,
            common_points=common_points,
            differences=differences,
            conflicts=conflicts,
            support_status=support_status,
            refusal_reason=refusal_reason,
        )

    def _collect_citations(self, compare_result: GroundedCompareResult) -> list:
        citations: list = []
        seen: set[tuple[str, str]] = set()
        for point in (*compare_result.common_points, *compare_result.differences, *compare_result.conflicts):
            for evidence in (*point.left_evidence, *point.right_evidence):
                key = (evidence.doc_id, evidence.chunk_id)
                if key in seen:
                    continue
                seen.add(key)
                citations.append(
                    build_citation(
                        RetrievedChunk(
                            text=evidence.snippet,
                            doc_id=evidence.doc_id,
                            chunk_id=evidence.chunk_id,
                            source=evidence.source,
                            page=evidence.page,
                            anchor=evidence.anchor,
                            original_text=evidence.snippet,
                        )
                    )
                )
        return citations

    def _group_label(self, hit: RetrievedChunk) -> str:
        return hit.title or hit.source or hit.doc_id or "document"

    def _has_strong_group(self, group: _EvidenceGroup) -> bool:
        best_score = build_evidence(group.best_hit).score
        return best_score is None or float(best_score) <= PARTIAL_SUPPORT_DISTANCE

    def _hit_sort_key(self, hit: RetrievedChunk) -> tuple[float, str]:
        score = hit.rerank_score if hit.rerank_score is not None else hit.distance
        normalized_score = float(score) if score is not None else -1.0
        return (normalized_score, hit.chunk_id)

    def _looks_conflicting(self, left_text: str, right_text: str) -> bool:
        left_tokens = self._tokenize(left_text)
        right_tokens = self._tokenize(right_text)
        if not left_tokens or not right_tokens:
            return False
        overlap = len(left_tokens & right_tokens) / max(1, len(left_tokens | right_tokens))
        if overlap < _OVERLAP_THRESHOLD:
            return False
        left_numbers = set(_NUMBER_PATTERN.findall(left_text))
        right_numbers = set(_NUMBER_PATTERN.findall(right_text))
        if left_numbers and right_numbers and left_numbers != right_numbers:
            return True
        left_negated = bool(left_tokens & _NEGATION_WORDS)
        right_negated = bool(right_tokens & _NEGATION_WORDS)
        return left_negated != right_negated

    def _tokenize(self, text: str) -> set[str]:
        return {
            token
            for token in _TOKEN_PATTERN.findall(text.lower())
            if token not in _STOPWORDS
        }

    def _normalized_text(self, hit: RetrievedChunk) -> str:
        return " ".join(sorted(self._tokenize(hit.text)))

    def _preview(self, text: str, limit: int = 80) -> str:
        normalized = " ".join(text.strip().split())
        if len(normalized) <= limit:
            return normalized
        return f"{normalized[: limit - 3]}..."
