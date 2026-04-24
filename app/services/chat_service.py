"""Application service for grounded chat responses."""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Optional

from app.core.exceptions import ChatError
from app.llm.factory import get_generation_runtime
from app.llm.mock import INSUFFICIENT_EVIDENCE
from app.rag.retrieval_models import GroundedAnswer, RefusalReason, SupportStatus
from app.rag.retrieval_models import RetrievalFilters
from app.rag.postprocess import Compressor, Reranker, get_compressor, get_reranker
from app.rag.vectorstore import get_neighbor_chunks
from app.runtime import GenerationRuntime, RuntimeRequest
from app.services.grounded_generation import (
    assess_grounding,
    build_citation,
    build_context,
    build_evidence,
    evidence_matches_query,
    expand_evidence_windows,
    format_evidence_block,
    is_out_of_scope_knowledge_query,
    OUT_OF_SCOPE_ANSWER,
    select_grounded_hits,
)
from app.services.search_service import SearchService
from app.services.service_models import ChatServiceResult, RetrievalStats, ServiceIssue, UseCaseMetadata, UseCaseTiming
from ports.llm import LLMProvider

logger = logging.getLogger(__name__)

_LATIN_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]+")
_CJK_STOP_CHARS = frozenset("\u7684\u4e86\u662f\u4ec0\u4e48\u4e00\u4e0b\u8bf7\u4e2a\u548c\u4e0e\u53ca\u5176\u4e2d")
_CHAT_DIRECTNESS_WEIGHT = 0.35
_CHAT_PRE_COMPRESS_SOURCE_CAP = 2
_CHAT_CANDIDATE_POOL_CAP = 32
_STRUCTURED_REF_LEXICAL_K = 5
_SOURCE_CONSISTENCY_LOOKAHEAD = 4
_STRUCTURED_REF_RE = re.compile(
    r"(?i)(?:\b(?:table|figure|fig\.?|algorithm)\s*(?:\d+|[ivxlcdm]+)\b|\bappendix\s+[a-z0-9]+\b|(?:表|图|算法)\s*[0-9一二三四五六七八九十]+|附录\s*[A-Za-z0-9一二三四五六七八九十]+)"
)
_SOURCE_POINTER_RE = re.compile(r"(?i)\b(?:this|the|milvus|rag|local)?\s*(?:paper|document|doc|file|pdf)\b")
_CROSS_SOURCE_INTENT_PHRASES = (
    "compare",
    "comparison",
    "contrast",
    "across documents",
    "across sources",
    "all documents",
    "all docs",
    "all sources",
    "multiple documents",
    "multiple docs",
    "these papers",
    "these documents",
    "these docs",
    "with the local",
    "with local",
    "多篇论文",
    "所有文档",
    "全部文档",
    "对比",
    "比较",
)
_LOCAL_DOC_INTENT_PHRASES = (
    "local docs",
    "local doc",
    "local document",
    "local documents",
    "local file",
    "local files",
    "local documentation",
    "project docs",
    "project doc",
    "project document",
    "project documents",
    "current docs",
    "current doc",
    "current document",
    "current documents",
    "本地文档",
    "当前文档",
    "这些文档",
    "项目文档",
    "本地文件",
)


@dataclass
class ChatService:
    """Retrieve-then-generate pipeline with explicit LangChain prompting."""

    search_service: SearchService = field(default_factory=SearchService)
    reranker: Reranker = field(default_factory=get_reranker)
    compressor: Compressor = field(default_factory=get_compressor)
    runtime: GenerationRuntime = field(default_factory=get_generation_runtime)
    llm: LLMProvider | None = None

    def chat(
        self,
        query: str,
        top_k: int,
        filters: RetrievalFilters | None = None,
        precomputed_hits: Optional[list] = None,
        debug: bool = False,
    ) -> ChatServiceResult:
        """Run the full RAG chat pipeline.

        Args:
            precomputed_hits: If provided, skip retrieval and use these hits directly.
                Allows the caller (e.g. the orchestrator) to run retrieval once and
                share the result across multiple services.
        """
        try:
            started = time.perf_counter()
            logger.info("Chat started: query_preview=%s top_k=%d", query[:60], top_k)
            if is_out_of_scope_knowledge_query(query):
                logger.info("Chat returning out-of-scope refusal before retrieval: query_preview=%s", query[:60])
                return self._refusal_result(
                    answer=OUT_OF_SCOPE_ANSWER,
                    started=started,
                    retrieval_ms=0.0,
                    retrieved_hits=0,
                    grounded_hits=0,
                    returned_hits=0,
                    empty_result=True,
                    refusal_reason=RefusalReason.OUT_OF_SCOPE,
                    issue_code="out_of_scope",
                    issue_message="Question is outside knowledge-base grounded answering scope.",
                    filters=filters,
                )

            retrieval_started = time.perf_counter()
            if precomputed_hits is not None:
                hits = precomputed_hits
                retrieval_ms = 0.0
            else:
                candidate_top_k = self._candidate_top_k(top_k)
                hits = self.search_service.retrieve(query=query, top_k=candidate_top_k, filters=filters)
                hits = self._inject_structured_reference_candidates(query, hits, filters)
                retrieval_ms = round((time.perf_counter() - retrieval_started) * 1000, 2)
            grounded_selection = select_grounded_hits(hits)
            grounded_hits = grounded_selection.hits
            if not grounded_hits:
                grounding = assess_grounding(retrieved_hits=hits, evidence=[])
                logger.info("Chat returning insufficient evidence: query_preview=%s", query[:60])
                return ChatServiceResult(
                    answer=INSUFFICIENT_EVIDENCE,
                    grounded_answer=GroundedAnswer(
                        answer=INSUFFICIENT_EVIDENCE,
                        evidence=(),
                        support_status=grounding.support_status,
                        refusal_reason=grounding.refusal_reason,
                    ),
                    citations=[],
                    metadata=UseCaseMetadata(
                        retrieved_count=0,
                        mode="grounded",
                        insufficient_evidence=True,
                        support_status=grounding.support_status.value,
                        refusal_reason=None if grounding.refusal_reason is None else grounding.refusal_reason.value,
                        empty_result=not hits,
                        warnings=("Insufficient grounded evidence for chat response.",),
                        issues=(
                            ServiceIssue(
                                code="insufficient_evidence",
                                message="Insufficient grounded evidence for chat response.",
                                severity="info",
                            ),
                        ),
                        timing=UseCaseTiming(
                            total_ms=round((time.perf_counter() - started) * 1000, 2),
                            retrieval_ms=retrieval_ms,
                        ),
                        runtime_mode=getattr(self.runtime, "runtime_name", type(self.runtime).__name__),
                        provider_mode=type(self.llm).__name__ if self.llm is not None else getattr(self.runtime, "provider_name", None),
                        filter_applied=filters is not None,
                        retrieval_stats=RetrievalStats(
                            retrieved_hits=len(hits),
                            grounded_hits=0,
                            returned_hits=0,
                        ),
                    ),
                    context=None,
                )

            if not evidence_matches_query(query, grounded_hits):
                logger.info("Chat returning insufficient evidence after relevance gate: query_preview=%s", query[:60])
                return self._refusal_result(
                    answer=INSUFFICIENT_EVIDENCE,
                    started=started,
                    retrieval_ms=retrieval_ms,
                    retrieved_hits=len(hits),
                    grounded_hits=len(grounded_hits),
                    returned_hits=0,
                    empty_result=False,
                    refusal_reason=RefusalReason.NO_RELEVANT_EVIDENCE,
                    issue_code="evidence_query_mismatch",
                    issue_message="Retrieved evidence does not match the query closely enough for a grounded answer.",
                    filters=filters,
                )

            rerank_started = time.perf_counter()
            reranked_hits = self.reranker.rerank(query=query, hits=grounded_hits)
            reranked_hits = self._rerank_direct_chat_evidence(query, reranked_hits)
            reranked_hits = self._prioritize_structured_reference_hits(query, reranked_hits)
            reranked_hits = self._prioritize_local_doc_hits(query, reranked_hits, filters)
            reranked_hits = self._apply_precompress_source_cap(
                reranked_hits,
                _CHAT_PRE_COMPRESS_SOURCE_CAP,
            )
            reranked_hits = self._apply_source_consistency_cap(query, reranked_hits, top_k, filters)
            reranked_hits = reranked_hits[:top_k]
            windowed_hits = expand_evidence_windows(
                reranked_hits,
                neighbor_loader=self._load_evidence_neighbors,
            )
            rerank_ms = round((time.perf_counter() - rerank_started) * 1000, 2)
            compress_started = time.perf_counter()
            compressed_hits = self.compressor.compress(query=query, hits=windowed_hits)
            compress_ms = round((time.perf_counter() - compress_started) * 1000, 2)
            compressed_hits = self._dedupe_compressed_chat_hits(compressed_hits)
            context = build_context(compressed_hits)
            prompt_inputs = {
                "query": query,
                "evidence_block": format_evidence_block(context),
            }
            prompt = self._build_prompt()
            if debug:
                logger.debug(
                    "Formatted chat prompt:\n%s",
                    self._format_prompt_for_debug(prompt, prompt_inputs),
                )
            generation_started = time.perf_counter()
            runtime_response = self.runtime.generate(
                RuntimeRequest(
                    prompt=prompt,
                    inputs=prompt_inputs,
                    fallback_query=query,
                    fallback_evidence=context.to_evidence_items(),
                    llm_override=self.llm,
                )
            )
            answer = runtime_response.text
            generation_ms = round((time.perf_counter() - generation_started) * 1000, 2)
            citations = [build_citation(hit) for hit in compressed_hits]
            evidence = [build_evidence(hit) for hit in compressed_hits]
            grounding = assess_grounding(retrieved_hits=hits, evidence=evidence)

            logger.info(
                "Chat completed: query_preview=%s grounded=%d reranked=%d compressed=%d",
                query[:60], len(grounded_hits), len(windowed_hits), len(compressed_hits),
            )
            return ChatServiceResult(
                answer=answer,
                citations=citations,
                grounded_answer=GroundedAnswer(
                    answer=answer,
                    evidence=tuple(evidence),
                    support_status=grounding.support_status,
                    refusal_reason=grounding.refusal_reason,
                ),
                metadata=UseCaseMetadata(
                    retrieved_count=len(compressed_hits),
                    mode="grounded",
                    support_status=grounding.support_status.value,
                    refusal_reason=None if grounding.refusal_reason is None else grounding.refusal_reason.value,
                    timing=UseCaseTiming(
                        total_ms=round((time.perf_counter() - started) * 1000, 2),
                        retrieval_ms=retrieval_ms,
                        rerank_ms=rerank_ms,
                        compress_ms=compress_ms,
                        generation_ms=generation_ms,
                    ),
                    runtime_mode=getattr(self.runtime, "runtime_name", type(self.runtime).__name__),
                    provider_mode=type(self.llm).__name__ if self.llm is not None else runtime_response.provider_name,
                    fallback_used=runtime_response.used_fallback,
                    filter_applied=filters is not None,
                    retrieval_stats=RetrievalStats(
                        retrieved_hits=len(hits),
                        grounded_hits=len(grounded_hits),
                        reranked_hits=len(windowed_hits),
                        returned_hits=len(compressed_hits),
                    ),
                ),
                context=context,
            )

        except Exception as exc:
            logger.exception("Chat failed: query_preview=%s", query[:60])
            raise ChatError(detail=f"Chat generation failed: {exc}") from exc

    def _refusal_result(
        self,
        *,
        answer: str,
        started: float,
        retrieval_ms: float,
        retrieved_hits: int,
        grounded_hits: int,
        returned_hits: int,
        empty_result: bool,
        refusal_reason: RefusalReason,
        issue_code: str,
        issue_message: str,
        filters: RetrievalFilters | None,
    ) -> ChatServiceResult:
        return ChatServiceResult(
            answer=answer,
            grounded_answer=GroundedAnswer(
                answer=answer,
                evidence=(),
                support_status=SupportStatus.INSUFFICIENT_EVIDENCE,
                refusal_reason=refusal_reason,
            ),
            citations=[],
            metadata=UseCaseMetadata(
                retrieved_count=0,
                mode="grounded",
                insufficient_evidence=True,
                support_status=SupportStatus.INSUFFICIENT_EVIDENCE.value,
                refusal_reason=refusal_reason.value,
                empty_result=empty_result,
                warnings=(issue_message,),
                issues=(
                    ServiceIssue(
                        code=issue_code,
                        message=issue_message,
                        severity="info",
                    ),
                ),
                timing=UseCaseTiming(
                    total_ms=round((time.perf_counter() - started) * 1000, 2),
                    retrieval_ms=retrieval_ms,
                ),
                runtime_mode=getattr(self.runtime, "runtime_name", type(self.runtime).__name__),
                provider_mode=type(self.llm).__name__ if self.llm is not None else getattr(self.runtime, "provider_name", None),
                filter_applied=filters is not None,
                retrieval_stats=RetrievalStats(
                    retrieved_hits=retrieved_hits,
                    grounded_hits=grounded_hits,
                    returned_hits=returned_hits,
                ),
            ),
            context=None,
        )

    def _build_prompt(self):
        try:
            from langchain_core.prompts import ChatPromptTemplate
        except ModuleNotFoundError:
            return "minddock-grounded-chat-prompt"

        return ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    (
                        "You are MindDock's grounded answer assistant. "
                        "Follow these rules strictly: "
                        "1. Answer only from the provided evidence; do not add outside knowledge. "
                        "2. If the evidence is missing, weak, contradictory, or not clearly aligned with the question, "
                        "say the evidence is insufficient and briefly explain the gap. "
                        "3. Synthesize all relevant evidence items; do not rely on the first item when other evidence "
                        "adds, qualifies, or conflicts with it. "
                        "4. If only part of the question is supported, answer that part and state what is not supported. "
                        "Keep the answer concise and factual."
                    ),
                ),
                (
                    "human",
                    "Question:\n{query}\n\nEvidence:\n{evidence_block}",
                ),
            ]
        )

    def _format_prompt_for_debug(self, prompt, inputs: dict[str, object]) -> str:
        if hasattr(prompt, "format_prompt"):
            return prompt.format_prompt(**inputs).to_string()
        if hasattr(prompt, "format"):
            return str(prompt.format(**inputs))
        return f"{prompt}\n\nInputs:\n{inputs}"

    def _load_evidence_neighbors(self, hit, before: int, after: int) -> list:
        return get_neighbor_chunks(hit, before=before, after=after)

    def _candidate_top_k(self, top_k: int) -> int:
        if top_k <= 0:
            return top_k
        return min(max(top_k * 4, top_k + 12), _CHAT_CANDIDATE_POOL_CAP)

    def _inject_structured_reference_candidates(
        self,
        query: str,
        hits: list,
        filters: RetrievalFilters | None,
    ) -> list:
        if not self._has_structured_reference_intent(query):
            return hits

        retrieve_structured = getattr(self.search_service, "retrieve_structured_reference_candidates", None)
        if retrieve_structured is None:
            return hits

        lexical_hits = retrieve_structured(
            query=query,
            top_k=_STRUCTURED_REF_LEXICAL_K,
            filters=filters,
        )
        if not lexical_hits:
            return hits

        lexical_ids = {getattr(hit, "chunk_id", "") for hit in lexical_hits if getattr(hit, "chunk_id", "")}
        merged = [
            self._mark_structured_reference_hit(hit) if getattr(hit, "chunk_id", "") in lexical_ids else hit
            for hit in hits
        ]
        seen = {getattr(hit, "chunk_id", "") for hit in merged if getattr(hit, "chunk_id", "")}
        for hit in lexical_hits:
            chunk_id = getattr(hit, "chunk_id", "")
            if chunk_id and chunk_id in seen:
                continue
            merged.append(self._mark_structured_reference_hit(hit))
            if chunk_id:
                seen.add(chunk_id)
        return merged

    def _has_structured_reference_intent(self, query: str) -> bool:
        return bool(_STRUCTURED_REF_RE.search(query))

    def _mark_structured_reference_hit(self, hit):
        extra_metadata = dict(getattr(hit, "extra_metadata", {}) or {})
        extra_metadata["retrieval_reason"] = "structured_ref_lexical"
        return hit.with_updates(extra_metadata=extra_metadata)

    def _prioritize_structured_reference_hits(self, query: str, hits: list) -> list:
        if not hits or not self._has_structured_reference_intent(query):
            return hits

        structured_hits = [
            hit
            for hit in hits
            if (getattr(hit, "extra_metadata", {}) or {}).get("retrieval_reason") == "structured_ref_lexical"
        ]
        if not structured_hits:
            return hits
        structured_ids = {getattr(hit, "chunk_id", "") for hit in structured_hits}
        remaining = [hit for hit in hits if getattr(hit, "chunk_id", "") not in structured_ids]
        return structured_hits + remaining

    def _prioritize_local_doc_hits(self, query: str, hits: list, filters: RetrievalFilters | None) -> list:
        if not hits or not self._has_local_docs_intent(query):
            return hits
        if filters is not None and filters.sources:
            return hits

        local_hits = [hit for hit in hits if self._is_local_markdown_source(hit)]
        if not local_hits:
            return hits
        return local_hits

    def _apply_source_consistency_cap(
        self,
        query: str,
        hits: list,
        top_k: int,
        filters: RetrievalFilters | None,
    ) -> list:
        if len(hits) <= 1 or top_k <= 1:
            return hits
        if filters is not None and filters.sources:
            return hits
        if self._has_local_docs_intent(query) or self._has_cross_source_intent(query):
            return hits

        preferred_source = self._chat_source_key(hits[0])
        if not preferred_source:
            return hits
        if not self._should_apply_source_consistency(query, hits, top_k, preferred_source):
            return hits

        preferred = [hit for hit in hits if self._chat_source_key(hit) == preferred_source]
        if len(preferred) < 2:
            return hits
        others = [hit for hit in hits if self._chat_source_key(hit) != preferred_source]
        return preferred + others

    def _should_apply_source_consistency(
        self,
        query: str,
        hits: list,
        top_k: int,
        preferred_source: str,
    ) -> bool:
        if self._has_structured_reference_intent(query) and self._has_source_pointer_intent(query):
            return True

        lookahead = min(len(hits), max(top_k, _SOURCE_CONSISTENCY_LOOKAHEAD))
        front = hits[:lookahead]
        preferred_count = sum(1 for hit in front if self._chat_source_key(hit) == preferred_source)
        return preferred_count >= 2 and preferred_count / max(lookahead, 1) >= 0.5

    def _has_source_pointer_intent(self, query: str) -> bool:
        return bool(_SOURCE_POINTER_RE.search(query))

    def _has_cross_source_intent(self, query: str) -> bool:
        normalized = " ".join(query.lower().split())
        if not normalized:
            return False
        return any(phrase in normalized for phrase in _CROSS_SOURCE_INTENT_PHRASES)

    def _has_local_docs_intent(self, query: str) -> bool:
        normalized = " ".join(query.lower().split())
        if not normalized:
            return False
        return any(phrase in normalized for phrase in _LOCAL_DOC_INTENT_PHRASES)

    def _is_local_markdown_source(self, hit) -> bool:
        candidates = [
            getattr(hit, "source", ""),
            getattr(hit, "title", ""),
            str((getattr(hit, "extra_metadata", {}) or {}).get("source_path") or ""),
            str((getattr(hit, "extra_metadata", {}) or {}).get("source") or ""),
        ]
        return any(self._has_markdown_extension(candidate) for candidate in candidates)

    def _has_markdown_extension(self, value: str) -> bool:
        normalized = value.strip().lower()
        return normalized.endswith(".md") or normalized.endswith(".markdown")

    def _rerank_direct_chat_evidence(self, query: str, hits: list) -> list:
        """Nudge chat evidence toward passages that directly answer the question."""

        if len(hits) <= 1:
            return hits

        rescored = []
        for index, hit in enumerate(hits):
            base_score = self._base_rerank_score(hit)
            directness = self._directness_score(query, hit)
            total = base_score + (_CHAT_DIRECTNESS_WEIGHT * directness)
            rescored.append((total, base_score, -index, hit.with_updates(rerank_score=round(total, 6))))

        rescored.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
        return [hit for _, _, _, hit in rescored]

    def _chat_source_key(self, hit) -> str:
        extra_metadata = getattr(hit, "extra_metadata", {}) or {}
        return (
            getattr(hit, "source", None)
            or getattr(hit, "doc_id", None)
            or getattr(hit, "source_id", None)
            or extra_metadata.get("source")
            or extra_metadata.get("source_id")
            or extra_metadata.get("doc_id")
            or ""
        )

    def _apply_precompress_source_cap(self, hits: list, cap: int) -> list:
        """Keep rank order stable while moving same-source overflow behind the capped front segment."""
        if len(hits) <= cap:
            return hits

        source_counts: dict[str, int] = {}
        result = []
        overflow = []

        for hit in hits:
            source = self._chat_source_key(hit)
            count = source_counts.get(source, 0)
            if count < cap:
                result.append(hit)
                source_counts[source] = count + 1
            else:
                overflow.append(hit)

        return result + overflow

    def _chat_evidence_text(self, hit) -> str:
        return (
            getattr(hit, "compressed_text", None)
            or getattr(hit, "text", None)
            or getattr(hit, "original_text", None)
            or ""
        )

    def _chat_doc_key(self, hit) -> str:
        extra_metadata = getattr(hit, "extra_metadata", {}) or {}
        return (
            getattr(hit, "doc_id", None)
            or getattr(hit, "source", None)
            or getattr(hit, "source_id", None)
            or extra_metadata.get("doc_id")
            or extra_metadata.get("source")
            or extra_metadata.get("source_id")
            or ""
        )

    def _normalize_evidence_text(self, text: str) -> str:
        normalized = re.sub(r"[^\w\s\u4e00-\u9fff]", " ", text.lower())
        return " ".join(normalized.split())

    def _is_light_duplicate(self, kept_hit, candidate_hit) -> bool:
        kept_text = self._normalize_evidence_text(self._chat_evidence_text(kept_hit))
        candidate_text = self._normalize_evidence_text(self._chat_evidence_text(candidate_hit))
        if not kept_text or not candidate_text:
            return False
        if kept_text == candidate_text:
            return True

        same_document = self._chat_doc_key(kept_hit) == self._chat_doc_key(candidate_hit)
        same_source = self._chat_source_key(kept_hit) == self._chat_source_key(candidate_hit)
        if not (same_document or same_source):
            return False

        shorter, longer = sorted((kept_text, candidate_text), key=len)
        if len(shorter) >= 80 and shorter in longer and len(shorter) / max(len(longer), 1) >= 0.8:
            return True

        kept_tokens = set(kept_text.split())
        candidate_tokens = set(candidate_text.split())
        if len(kept_tokens) < 8 or len(candidate_tokens) < 8:
            return False
        overlap = len(kept_tokens & candidate_tokens) / max(min(len(kept_tokens), len(candidate_tokens)), 1)
        return overlap >= 0.92

    def _dedupe_compressed_chat_hits(self, hits: list) -> list:
        """Remove only obvious duplicates from compressed chat hits before context assembly."""
        kept = []
        for hit in hits:
            if any(self._is_light_duplicate(kept_hit, hit) for kept_hit in kept):
                continue
            kept.append(hit)
        return kept

    def _base_rerank_score(self, hit) -> float:
        if hit.rerank_score is not None:
            return float(hit.rerank_score)
        if hit.distance is None:
            return 0.0
        return 1.0 / (1.0 + max(float(hit.distance), 0.0))

    def _directness_score(self, query: str, hit) -> float:
        text = " ".join(
            part.strip()
            for part in (
                hit.text,
                getattr(hit, "title", ""),
                getattr(hit, "section", ""),
                getattr(hit, "location", ""),
                getattr(hit, "ref", ""),
            )
            if part and part.strip()
        )
        query_tokens = _directness_tokens(query)
        text_tokens = _directness_tokens(text)
        if not query_tokens or not text_tokens:
            lexical = 0.0
        else:
            overlap = query_tokens.intersection(text_tokens)
            lexical = len(overlap) / max(len(query_tokens), 1)

        normalized_query = query.lower()
        normalized_text = text.lower()
        cue_score = self._answer_cue_score(normalized_query, normalized_text)
        noise_penalty = self._noise_penalty(normalized_text)
        return max(0.0, lexical + cue_score - noise_penalty)

    def _answer_cue_score(self, query: str, text: str) -> float:
        score = 0.0
        if _contains_any(query, ("\u6311\u6218", "\u56f0\u96be", "\u95ee\u9898", "challenge", "difficulty")):
            if _contains_any(
                text,
                (
                    "\u6311\u6218",
                    "\u56f0\u96be",
                    "\u95ee\u9898",
                    "\u9650\u5236",
                    "\u4e0d\u8db3",
                    "challenge",
                    "limitation",
                    "issue",
                    "problem",
                    "difficulty",
                ),
            ):
                score += 0.35
        if _contains_any(query, ("\u89e3\u51b3", "\u4ec0\u4e48\u662f", "solve", "address")):
            if _contains_any(
                text,
                (
                    "\u89e3\u51b3",
                    "\u7f13\u89e3",
                    "solve",
                    "address",
                    "mitigate",
                    "reduce",
                    "hallucination",
                    "outdated knowledge",
                    "retrieval-augmented generation",
                ),
            ):
                score += 0.3
        if "rag" in query:
            if _contains_any(
                text,
                (
                    "retrieval-augmented generation",
                    "retrieval augmented generation",
                    "retriev",
                    "generation",
                ),
            ):
                score += 0.25
            if "\u4ec0\u4e48\u662f" in query and "retrieval-augmented generation" in text:
                score += 0.25
                if _contains_any(text, (" is a ", " has emerged as ", " refers to ")):
                    score += 0.15
        return score

    def _noise_penalty(self, text: str) -> float:
        compact = "".join(ch for ch in text if not ch.isspace())
        if not compact:
            return 0.0
        digit_ratio = sum(ch.isdigit() for ch in compact) / len(compact)
        alpha_cjk_ratio = sum(ch.isalpha() or "\u4e00" <= ch <= "\u9fff" for ch in compact) / len(compact)
        penalty = 0.0
        if digit_ratio > 0.35:
            penalty += 0.35
        if alpha_cjk_ratio < 0.45:
            penalty += 0.25
        if "key words" in text or "keywords" in text:
            penalty += 0.1
        return penalty


def _directness_tokens(text: str) -> set[str]:
    tokens = {token.lower() for token in _LATIN_TOKEN_RE.findall(text) if len(token) > 1 or token.lower() == "rag"}
    for match in _CJK_RE.findall(text):
        chars = [char for char in match if char not in _CJK_STOP_CHARS]
        tokens.update(chars)
        tokens.update("".join(chars[index : index + 2]) for index in range(len(chars) - 1))
    return {token for token in tokens if token}


def _contains_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(needle in text for needle in needles)
