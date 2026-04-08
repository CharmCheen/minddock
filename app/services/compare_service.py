"""Application service for grounded multi-document compare workflows."""

from __future__ import annotations

import logging
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field

from app.core.exceptions import ChatError
from app.llm.mock import INSUFFICIENT_EVIDENCE
from app.rag.retrieval_models import ComparedPoint, GroundedCompareResult, RefusalReason, RetrievalFilters, RetrievedChunk, SupportStatus
from app.rag.postprocess import Compressor, Reranker, get_compressor, get_reranker
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
    """Deterministic grounded compare workflow over retrieved evidence groups."""

    search_service: SearchService = field(default_factory=SearchService)
    reranker: Reranker = field(default_factory=get_reranker)
    compressor: Compressor = field(default_factory=get_compressor)
    collection: object = field(default=None)

    def compare(self, *, question: str, top_k: int, filters: RetrievalFilters | None = None) -> CompareServiceResult:
        try:
            started = time.perf_counter()
            logger.info("Compare started: question_preview=%s top_k=%d", question[:60], top_k)

            retrieval_started = time.perf_counter()
            hits = self.search_service.retrieve(query=question, top_k=top_k, filters=filters)
            retrieval_ms = round((time.perf_counter() - retrieval_started) * 1000, 2)
            grounded_hits = select_grounded_hits(hits).hits
            if not grounded_hits:
                return self._insufficient_result(
                    question=question,
                    hits=hits,
                    retrieval_ms=retrieval_ms,
                    started=started,
                    filters=filters,
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
                )

            left_group, right_group = groups[:2]
            common_points, differences, conflicts = self._compare_groups(question=question, left_group=left_group, right_group=right_group)
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
                    ),
                    filter_applied=filters is not None,
                    retrieval_stats=RetrievalStats(
                        retrieved_hits=len(hits),
                        grounded_hits=len(grounded_hits),
                        reranked_hits=len(reranked_hits),
                        returned_hits=len(compressed_hits),
                    ),
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
            ),
            context=None if not returned_hits else build_context(returned_hits),
        )

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
