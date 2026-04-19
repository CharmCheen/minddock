"""Application service for grounded multi-document compare workflows."""

from __future__ import annotations

import logging
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

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


@dataclass
class CompareConfig:
    """Optional configuration for the compare workflow.

    Setting ``enable_llm_conflict_detection=True`` adds a lightweight LLM step
    (timeout 200ms) to double-check whether candidate conflicting sentences
    actually contradict each other, reducing false-positive conflict flags.
    """

    enable_llm_conflict_detection: bool = False
    llm_timeout_ms: int = 200


# Compare query decomposition patterns
_COMPARE_SEPARATORS = [
    re.compile(r"\bvs?\b", re.IGNORECASE),  # "vs" or "versus"
    re.compile(r"\bversus\b", re.IGNORECASE),
    re.compile(r"\band\b", re.IGNORECASE),  # "A and B"
    re.compile(r"\bcompare[d]?\s+(.+?)\s+(?:with|to|and)\s+(.+)", re.IGNORECASE),  # "compare A with/to B"
    re.compile(r"\bcompare\s+(.+?)\s+(?:and|with|to)\s+(.+)", re.IGNORECASE),  # "compare A and B"
    re.compile(r"\b(difference|compare|contrast)\b", re.IGNORECASE),  # "difference between A and B"
]


def _decompose_compare_query(question: str) -> Optional[tuple[str, str]]:
    """Try to decompose a compare query into two sub-queries.

    Returns (sub_q1, sub_q2) if decomposition succeeds, None otherwise.

    Examples:
        "Compare A and B" -> ("A", "B")
        "Compare A vs B" -> ("A", "B")
        "difference between A and B" -> ("A", "B")
    """
    original = question

    # Normalize: strip the question framing
    question = re.sub(r"^\s*how?\s+(do|does|did|is|are|can|should)\s+", "", question, flags=re.IGNORECASE)
    question = re.sub(r"\s*(how|what|why|when|where|who|which)\s*$", "", question, flags=re.IGNORECASE)
    question = question.strip().rstrip("?").strip()

    # Pattern: "compare A and B" or "compare A vs B" or "compare A with B"
    m = re.match(r"^compare\s+(.+?)\s+(?:and|vs|versus|with|to)\s+(.+)$", question, re.IGNORECASE)
    if m:
        left, right = m.group(1).strip(), m.group(2).strip()
        if left and right and left.lower() != right.lower():
            return (left, right)

    # Chinese compare patterns (explicit extract, not split)
    _CN_PATTERNS = [
        (r"对比\s*(\S+?)\s*[和与跟和]\s*(\S+)$", 1, 2),  # "对比A和B"
        (r"比较\s*(\S+?)\s*[和与跟和]\s*(\S+)$", 1, 2),  # "比较A与B"
        (r"(\S+)\s*[和与跟和]\s*(\S+)\s*(?:区别|差异|不同)", 1, 2),  # "A和B的区别"
        (r"(?:区别|差异)\s*[在于]?\s*(\S+)\s*[和与跟和]\s*(\S+)", 1, 2),  # "区别于A和B"
    ]
    for pat, g1, g2 in _CN_PATTERNS:
        m = re.match(pat, question)
        if m:
            left, right = m.group(g1).strip(), m.group(g2).strip()
            if left and right and left != right:
                return (left, right)

    # Pattern: "A vs B" or "A and B" (after stripping question framing)
    for sep_re in _COMPARE_SEPARATORS:
        parts = sep_re.split(question)
        if len(parts) == 2:
            left, right = parts[0].strip(), parts[1].strip()
            # Clean up common prefixes
            left = re.sub(r"^(and|with|to|for)\s+", "", left, flags=re.IGNORECASE).strip()
            right = re.sub(r"^(and|with|to|for)\s+", "", right, flags=re.IGNORECASE).strip()
            if left and right and left.lower() != right.lower():
                return (left, right)

    # Pattern: "difference between A and B"
    m = re.match(r"^(?:difference\s+between|compare\s+)\s*(.+?)\s+(?:and|vs|versus|with)\s+(.+)$", question, re.IGNORECASE)
    if m:
        left, right = m.group(1).strip(), m.group(2).strip()
        if left and right and left.lower() != right.lower():
            return (left, right)

    return None


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
    config: CompareConfig | None = None

    def compare(
        self,
        *,
        question: str,
        top_k: int,
        filters: RetrievalFilters | None = None,
        precomputed_hits: Optional[list] = None,
        max_distance_threshold: float | None = None,
        partial_support_distance: float | None = None,
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
                decomposed = _decompose_compare_query(question)
                if decomposed:
                    sub_q1, sub_q2 = decomposed
                    logger.info("Compare query decomposed: sub_q1=%s sub_q2=%s", sub_q1[:40], sub_q2[:40])
                    per_sub_k = max(top_k, 3)  # Retrieve enough candidates from each sub-query
                    hits_a = self.search_service.retrieve(query=sub_q1, top_k=per_sub_k, filters=filters)
                    hits_b = self.search_service.retrieve(query=sub_q2, top_k=per_sub_k, filters=filters)
                    merged_hits = self._merge_dual_hits(hits_a, hits_b, top_k=top_k)
                    merged_doc_ids = set(h.doc_id for h in merged_hits if h.doc_id)
                    if len(merged_doc_ids) >= 2:
                        hits = merged_hits
                    else:
                        logger.info("Dual retrieval insufficient diversity, falling back")
                        hits = self.search_service.retrieve(query=question, top_k=top_k, filters=filters)
                else:
                    hits = self.search_service.retrieve(query=question, top_k=top_k, filters=filters)
                retrieval_ms = round((time.perf_counter() - retrieval_started) * 1000, 2)
            grounded_hits = select_grounded_hits(hits, max_distance_threshold=max_distance_threshold).hits
            if not grounded_hits:
                return self._insufficient_result(
                    question=question,
                    hits=hits,
                    retrieval_ms=retrieval_ms,
                    started=started,
                    filters=filters,
                    partial_support_distance=partial_support_distance,
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
                    partial_support_distance=partial_support_distance,
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
                partial_support_distance=partial_support_distance,
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
        partial_support_distance: float | None = None,
    ) -> CompareServiceResult:
        compare_result = GroundedCompareResult(
            query=question,
            support_status=SupportStatus.INSUFFICIENT_EVIDENCE,
            refusal_reason=assess_grounding(retrieved_hits=hits, evidence=[], partial_support_distance=partial_support_distance).refusal_reason if reason is None else None,
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
        partial_support_distance: float | None = None,
    ) -> GroundedCompareResult:
        evidence = [
            item
            for point in (*common_points, *differences, *conflicts)
            for item in (*point.left_evidence, *point.right_evidence)
        ]
        grounding = assess_grounding(retrieved_hits=hits, evidence=evidence, partial_support_distance=partial_support_distance)
        support_status = grounding.support_status
        refusal_reason = grounding.refusal_reason
        if conflicts:
            support_status = SupportStatus.CONFLICTING_EVIDENCE
            refusal_reason = None
        elif differences and not (self._has_strong_group(left_group, partial_support_distance) and self._has_strong_group(right_group, partial_support_distance)):
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
                            title=evidence.title,
                            section=evidence.section,
                            location=evidence.location,
                            ref=evidence.ref,
                            original_text=evidence.snippet,
                            extra_metadata={
                                'block_id': evidence.block_id,
                                'section_path': evidence.section_path,
                                'highlighted_sentence': evidence.highlighted_sentence,
                                'position_start': evidence.position_start,
                                'position_end': evidence.position_end,
                            },
                        )
                    )
                )
        return citations

    def _group_label(self, hit: RetrievedChunk) -> str:
        return hit.title or hit.source or hit.doc_id or "document"

    def _has_strong_group(self, group: _EvidenceGroup, partial_support_distance: float | None = None) -> bool:
        threshold = partial_support_distance if partial_support_distance is not None else PARTIAL_SUPPORT_DISTANCE
        best = group.best_hit
        # Use distance (not rerank_score) for threshold: rerank_score is a composite
        # heuristic with range ~0-2.5, while PARTIAL_SUPPORT_DISTANCE=1.0 is calibrated
        # for raw cosine distance (0-1). Using rerank_score here would make the
        # threshold nearly always pass (since most rerank_scores > 1.0).
        score = best.distance if best.distance is not None else best.rerank_score
        return score is None or float(score) <= threshold

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
        heuristic_conflict = left_negated != right_negated

        if not heuristic_conflict:
            return False

        # LLM double-check: only performed when heuristic flags a conflict
        # to reduce false positives without adding latency on every pair.
        if self.config is not None and self.config.enable_llm_conflict_detection:
            return self._llm_is_conflicting(left_text, right_text)

        return True

    def _llm_is_conflicting(self, left_text: str, right_text: str) -> bool:
        """Use LLM to determine if two texts contradict each other.

        Lightweight: single short prompt, {llm_timeout_ms} ms timeout.
        Returns True only when LLM explicitly says YES (contradiction).
        Falls back to heuristic result on timeout or error.
        """
        import threading
        timeout_ms = (self.config.llm_timeout_ms or 200) if self.config else 200

        result: dict[str, bool] = {"value": True}  # fallback

        def _call_llm() -> None:
            try:
                from app.llm.factory import get_llm_provider
                provider = get_llm_provider()
                prompt = (
                    f"Do these two sentences contradict each other? "
                    f"Answer only YES or NO.\n"
                    f"1. {left_text[:300]}\n"
                    f"2. {right_text[:300]}\n"
                )
                response = provider.complete(prompt=prompt, max_tokens=5, temperature=0)
                result["value"] = "yes" in response.strip().lower()[:5]
            except Exception:
                result["value"] = True  # on error, trust heuristic

        thread = threading.Thread(target=_call_llm, daemon=True)
        thread.start()
        thread.join(timeout=timeout_ms / 1000.0)
        if thread.is_alive():
            logger.warning("LLM conflict check timed out after %dms, trusting heuristic", timeout_ms)
            return True
        return result["value"]

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

    def _merge_dual_hits(
        self,
        hits_a: list[RetrievedChunk],
        hits_b: list[RetrievedChunk],
        *,
        top_k: int,
    ) -> list[RetrievedChunk]:
        """Merge hits from two sub-queries ensuring both topics are represented.

        Strategy:
        1. Separate hits by provenance (a-only, b-only, dual-topic)
        2. Take at least 1 best hit from each of the two pure topics
        3. Sort remaining by relevance (distance) and fill up to top_k
        4. Apply doc-level dedup throughout
        """
        a_only: list[RetrievedChunk] = []
        b_only: list[RetrievedChunk] = []
        dual: list[RetrievedChunk] = []
        a_keys: set[tuple[str, str]] = set()

        for hit in hits_a:
            key = (hit.doc_id, hit.chunk_id)
            a_keys.add(key)
            a_only.append(hit)

        for hit in hits_b:
            key = (hit.doc_id, hit.chunk_id)
            if key in a_keys:
                dual.append(hit)  # appears in both sub-queries = dual-topic
            else:
                b_only.append(hit)

        # Sort each list by relevance (distance: lower is better)
        def _by_distance(h: RetrievedChunk) -> float:
            return h.distance if h.distance is not None else 999.0

        a_only.sort(key=_by_distance)
        b_only.sort(key=_by_distance)
        dual.sort(key=_by_distance)

        # Build result with diversity guarantee
        result: list[RetrievedChunk] = []
        result_doc_ids: set[str] = set()

        def _add(hit: RetrievedChunk) -> bool:
            doc_id = hit.doc_id
            if doc_id and doc_id not in result_doc_ids:
                result.append(hit)
                if doc_id:
                    result_doc_ids.add(doc_id)
                return True
            return False

        # 1. Best from each pure topic (at least 1 each)
        if a_only and not _add(a_only[0]):
            pass
        if b_only and not _add(b_only[0]):
            pass

        # 2. Dual-topic hits (relevant to both)
        for hit in dual:
            if len(result) >= top_k:
                break
            _add(hit)

        # 3. Remaining from each topic, sorted by relevance
        remaining = a_only[1:] + b_only[1:]
        remaining.sort(key=_by_distance)
        for hit in remaining:
            if len(result) >= top_k:
                break
            _add(hit)

        logger.debug(
            "Dual merge: a_only=%d b_only=%d dual=%d result=%d doc_ids=%s",
            len(a_only),
            len(b_only),
            len(dual),
            len(result),
            sorted(result_doc_ids),
        )
        return result
