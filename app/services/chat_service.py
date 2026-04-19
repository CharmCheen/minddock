"""Application service for grounded chat responses."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from app.core.exceptions import ChatError
from app.llm.factory import get_generation_runtime
from app.llm.mock import INSUFFICIENT_EVIDENCE
from app.rag.retrieval_models import GroundedAnswer
from app.rag.retrieval_models import RetrievalFilters
from app.rag.postprocess import Compressor, Reranker, get_compressor, get_reranker
from app.runtime import GenerationRuntime, RuntimeRequest
from app.services.grounded_generation import (
    assess_grounding,
    build_citation,
    build_context,
    build_evidence,
    format_evidence_block,
    select_grounded_hits,
)
from app.services.search_service import SearchService
from app.services.service_models import ChatServiceResult, RetrievalStats, ServiceIssue, UseCaseMetadata, UseCaseTiming
from ports.llm import LLMProvider

logger = logging.getLogger(__name__)


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
        max_distance_threshold: float | None = None,
        partial_support_distance: float | None = None,
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

            retrieval_started = time.perf_counter()
            if precomputed_hits is not None:
                hits = precomputed_hits
                retrieval_ms = 0.0
            else:
                hits = self.search_service.retrieve(query=query, top_k=top_k, filters=filters)
                retrieval_ms = round((time.perf_counter() - retrieval_started) * 1000, 2)
            grounded_selection = select_grounded_hits(hits, max_distance_threshold=max_distance_threshold)
            grounded_hits = grounded_selection.hits
            if not grounded_hits:
                grounding = assess_grounding(retrieved_hits=hits, evidence=[], partial_support_distance=partial_support_distance)
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
                        retrieved_count=len(hits),
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

            rerank_started = time.perf_counter()
            reranked_hits = self.reranker.rerank(query=query, hits=grounded_hits)
            rerank_ms = round((time.perf_counter() - rerank_started) * 1000, 2)
            compress_started = time.perf_counter()
            compressed_hits = self.compressor.compress(query=query, hits=reranked_hits)
            compress_ms = round((time.perf_counter() - compress_started) * 1000, 2)
            context = build_context(compressed_hits)
            prompt_inputs = {
                "query": query,
                "evidence_block": format_evidence_block(context),
            }
            generation_started = time.perf_counter()
            runtime_response = self.runtime.generate(
                RuntimeRequest(
                    prompt=self._build_prompt(),
                    inputs=prompt_inputs,
                    fallback_query=query,
                    fallback_evidence=context.to_evidence_items(),
                    llm_override=self.llm,
                )
            )
            answer = runtime_response.text
            generation_ms = round((time.perf_counter() - generation_started) * 1000, 2)
            citations = [build_citation(hit, query) for hit in compressed_hits]
            evidence = [build_evidence(hit, query) for hit in compressed_hits]
            grounding = assess_grounding(retrieved_hits=hits, evidence=evidence, partial_support_distance=partial_support_distance)

            logger.info(
                "Chat completed: query_preview=%s grounded=%d reranked=%d compressed=%d",
                query[:60], len(grounded_hits), len(reranked_hits), len(compressed_hits),
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
                    filter_applied=filters is not None,
                    retrieval_stats=RetrievalStats(
                        retrieved_hits=len(hits),
                        grounded_hits=len(grounded_hits),
                        reranked_hits=len(reranked_hits),
                        returned_hits=len(compressed_hits),
                    ),
                ),
                context=context,
            )

        except Exception as exc:
            logger.exception("Chat failed: query_preview=%s", query[:60])
            raise ChatError(detail=f"Chat generation failed: {exc}") from exc

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
                        "Use only the provided evidence. "
                        "If the evidence is insufficient, say so explicitly. "
                        "Keep the answer concise and factual."
                    ),
                ),
                (
                    "human",
                    "Question:\n{query}\n\nEvidence:\n{evidence_block}",
                ),
            ]
        )
