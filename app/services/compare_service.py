"""Application service for grounded multi-document compare workflows."""

from __future__ import annotations

import json
import logging
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

from app.core.exceptions import ChatError
from app.llm.factory import get_generation_runtime
from app.llm.mock import INSUFFICIENT_EVIDENCE
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
    select_grounded_hits,
)
from app.services.search_service import SearchService
from app.services.source_freshness import refresh_compare_result_freshness
from app.services.service_models import CompareServiceResult, RetrievalStats, ServiceIssue, UseCaseMetadata, UseCaseTiming
from app.services.workflow_trace import build_trace_warnings, final_source_summary, source_scope_trace
from ports.llm import LLMProvider

logger = logging.getLogger(__name__)

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

            retrieval_started = time.perf_counter()
            if precomputed_hits is not None:
                hits = precomputed_hits
                retrieval_ms = 0.0
            else:
                hits = self.search_service.retrieve(query=question, top_k=top_k, filters=filters)
                retrieval_ms = round((time.perf_counter() - retrieval_started) * 1000, 2)
            workflow_trace_base = {
                "operation": "compare",
                "requested_top_k": top_k,
                "internal_candidate_k": len(hits),
                **source_scope_trace(filters),
                "cross_document_intent_detected": True,
                "initial_candidate_count": len(hits),
                "applied_rules": [],
            }
            grounded_hits = select_grounded_hits(hits).hits
            if not grounded_hits:
                return self._insufficient_result(
                    question=question,
                    hits=hits,
                    retrieval_ms=retrieval_ms,
                    started=started,
                    filters=filters,
                    workflow_trace=self._finalize_insufficient_trace(workflow_trace_base),
                )

            rerank_started = time.perf_counter()
            reranked_hits = self.reranker.rerank(query=question, hits=grounded_hits)
            rerank_ms = round((time.perf_counter() - rerank_started) * 1000, 2)
            compress_started = time.perf_counter()
            compressed_hits = self.compressor.compress(query=question, hits=reranked_hits)
            compress_ms = round((time.perf_counter() - compress_started) * 1000, 2)

            groups = self._group_hits(compressed_hits)
            if len(groups) < 2:
                return self._insufficient_result(
                    question=question,
                    hits=hits,
                    grounded_hits=grounded_hits,
                    returned_hits=compressed_hits,
                    retrieval_ms=retrieval_ms,
                    rerank_ms=rerank_ms,
                    compress_ms=compress_ms,
                    started=started,
                    filters=filters,
                    reason="insufficient_context",
                    workflow_trace=self._finalize_insufficient_trace(
                        workflow_trace_base,
                        after_rerank_count=len(reranked_hits),
                        final_candidate_count=len(compressed_hits),
                        extra_warnings=("insufficient_context",),
                    ),
                )

            left_group, right_group = groups[:2]
            generation_started = time.perf_counter()
            common_points, differences, conflicts = self._compare_groups(
                question=question,
                left_group=left_group,
                right_group=right_group,
            )
            generation_ms = round((time.perf_counter() - generation_started) * 1000, 2)
            compare_result = self._build_compare_result(
                question=question,
                hits=hits,
                left_group=left_group,
                right_group=right_group,
                common_points=common_points,
                differences=differences,
                conflicts=conflicts,
            )
            compare_result = refresh_compare_result_freshness(compare_result, collection=self.collection)
            citations = self._collect_citations(compare_result)
            workflow_trace = {
                **workflow_trace_base,
                "after_rerank_count": len(reranked_hits),
                "final_candidate_count": len(compressed_hits),
                "final_citation_count": len(citations),
                "final_evidence_count": len(citations),
                "applied_rules": [],
                "final_sources": final_source_summary(citations),
                "trace_warnings": build_trace_warnings(citations=citations),
            }
            logger.info(
                "Compare completed: question_preview=%s groups=%d returned=%d",
                question[:60],
                len(groups),
                len(compressed_hits),
            )
            return CompareServiceResult(
                compare_result=compare_result,
                citations=citations,
                metadata=UseCaseMetadata(
                    retrieved_count=len(compressed_hits),
                    mode="grounded_compare",
                    insufficient_evidence=compare_result.support_status == SupportStatus.INSUFFICIENT_EVIDENCE,
                    support_status=compare_result.support_status.value,
                    refusal_reason=None if compare_result.refusal_reason is None else compare_result.refusal_reason.value,
                    timing=UseCaseTiming(
                        total_ms=round((time.perf_counter() - started) * 1000, 2),
                        retrieval_ms=retrieval_ms,
                        rerank_ms=rerank_ms,
                        compress_ms=compress_ms,
                        generation_ms=generation_ms,
                    ),
                    runtime_mode=getattr(self.runtime, "runtime_name", type(self.runtime).__name__),
                    provider_mode=type(self.llm).__name__ if self.llm is not None else getattr(self.runtime, "provider_name", None),
                    filter_applied=filters is not None,
                    retrieval_stats=RetrievalStats(
                        retrieved_hits=len(hits),
                        grounded_hits=len(grounded_hits),
                        reranked_hits=len(reranked_hits),
                        returned_hits=len(compressed_hits),
                    ),
                    workflow_trace=workflow_trace,
                ),
                context=build_context(compressed_hits),
            )
        except Exception as exc:
            logger.exception("Compare failed: question_preview=%s", question[:60])
            raise ChatError(detail=f"Compare generation failed: {exc}") from exc

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
        reason: str | None = None,
        workflow_trace: dict[str, object] | None = None,
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
                warnings=("Insufficient grounded evidence for compare response.",),
                issues=(
                    ServiceIssue(
                        code="insufficient_evidence",
                        message="Insufficient grounded evidence for compare response.",
                        severity="info",
                    ),
                ),
                timing=UseCaseTiming(
                    total_ms=round((time.perf_counter() - started) * 1000, 2),
                    retrieval_ms=retrieval_ms,
                    rerank_ms=rerank_ms,
                    compress_ms=compress_ms,
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
        lines: list[str] = [
            (
                "You are a grounded comparison assistant. "
                "Compare the evidence from two sources and produce a structured JSON response. "
                "Only use the evidence provided below. Do not add outside knowledge."
            ),
            "",
            f"Question: {question}",
            "",
            "Left source evidence:",
        ]
        for index, hit in enumerate(left_group.hits, start=1):
            lines.append(f"  L{index}: {hit.text.strip()}")
        lines.append("")
        lines.append("Right source evidence:")
        for index, hit in enumerate(right_group.hits, start=1):
            lines.append(f"  R{index}: {hit.text.strip()}")
        lines.extend([
            "",
            (
                "Return strictly valid JSON with this structure:\n"
                "{\n"
                '  "common_points": [\n'
                "    {\n"
                '      "statement": "string",\n'
                '      "summary_note": "string",\n'
                '      "left_evidence_ids": ["L1"],\n'
                '      "right_evidence_ids": ["R1"]\n'
                "    }\n"
                "  ],\n"
                '  "differences": [...],\n'
                '  "conflicts": [...]\n'
                "}"
            ),
            "",
            "Rules:",
            "1. Evidence ids MUST come from the L1..Ln and R1..Rn labels above.",
            "2. Every point must have evidence from BOTH sides. Omit any point that cannot be supported by both left and right evidence.",
            "3. Do not invent evidence IDs or output one-sided points.",
        ])
        return "\n".join(lines)

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

            points.append(
                ComparedPoint(
                    statement=statement,
                    left_evidence=left_evidence,
                    right_evidence=right_evidence,
                    summary_note=summary_note,
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
