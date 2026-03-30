"""Application service for minimal grounded summaries."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.core.exceptions import SummarizeError
from app.llm.factory import get_llm_provider
from app.llm.mock import INSUFFICIENT_EVIDENCE
from app.rag.postprocess import Compressor, Reranker, get_compressor, get_reranker
from app.services.grounded_generation import build_citation, build_context, select_grounded_hits
from app.services.search_service import SearchService
from ports.llm import LLMProvider

logger = logging.getLogger(__name__)


@dataclass
class SummarizeService:
    """Build a minimal retrieve-then-summarize pipeline with citations."""

    search_service: SearchService = field(default_factory=SearchService)
    reranker: Reranker = field(default_factory=get_reranker)
    compressor: Compressor = field(default_factory=get_compressor)
    llm: LLMProvider = field(default_factory=get_llm_provider)

    def summarize(self, topic: str, top_k: int, filters: dict[str, str] | None = None) -> dict[str, object]:
        try:
            logger.info("Summarize started: topic_preview=%s top_k=%d", topic[:60], top_k)

            hits = self.search_service.retrieve(query=topic, top_k=top_k, filters=filters)
            grounded_hits = select_grounded_hits(hits)
            if not grounded_hits:
                logger.info("Summarize returning insufficient evidence: topic_preview=%s", topic[:60])
                return {
                    "summary": INSUFFICIENT_EVIDENCE,
                    "citations": [],
                    "retrieved_count": 0,
                }

            reranked_hits = self.reranker.rerank(query=topic, hits=grounded_hits)
            compressed_hits = self.compressor.compress(query=topic, hits=reranked_hits)
            context = build_context(compressed_hits)
            logger.debug(
                "Summarize context assembled: topic_preview=%s grounded=%d reranked=%d compressed=%d context_chars=%d",
                topic[:60],
                len(grounded_hits),
                len(reranked_hits),
                len(compressed_hits),
                len(context),
            )
            summary_query = (
                "Summarize the topic using only the provided evidence. "
                "Keep it concise, grounded, and synthesis-oriented.\n"
                f"Topic: {topic}"
            )
            summary = self.llm.generate(query=summary_query, evidence=context)
            citations = [build_citation(hit) for hit in compressed_hits]

            logger.info(
                "Summarize completed: topic_preview=%s grounded=%d reranked=%d compressed=%d",
                topic[:60], len(grounded_hits), len(reranked_hits), len(compressed_hits),
            )

            return {
                "summary": summary,
                "citations": citations,
                "retrieved_count": len(compressed_hits),
            }
        except Exception as exc:
            logger.exception("Summarize failed: topic_preview=%s", topic[:60])
            raise SummarizeError(detail=f"Summarization failed: {exc}") from exc
