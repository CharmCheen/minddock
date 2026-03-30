"""Application service for grounded chat responses."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.core.exceptions import ChatError
from app.llm.factory import get_llm_provider
from app.llm.mock import INSUFFICIENT_EVIDENCE
from app.rag.postprocess import Compressor, Reranker, get_compressor, get_reranker
from app.services.grounded_generation import build_citation, build_context, select_grounded_hits
from app.services.search_service import SearchService
from ports.llm import LLMProvider

logger = logging.getLogger(__name__)


@dataclass
class ChatService:
    """Retrieve-then-generate pipeline with citations."""

    search_service: SearchService = field(default_factory=SearchService)
    reranker: Reranker = field(default_factory=get_reranker)
    compressor: Compressor = field(default_factory=get_compressor)
    llm: LLMProvider = field(default_factory=get_llm_provider)

    def chat(self, query: str, top_k: int, filters: dict[str, str] | None = None) -> dict[str, object]:
        """Run the full RAG chat pipeline.

        Raises:
            ChatError: If the pipeline encounters an unrecoverable error.
        """
        try:
            logger.info("Chat started: query_preview=%s top_k=%d", query[:60], top_k)

            hits = self.search_service.retrieve(query=query, top_k=top_k, filters=filters)
            grounded_hits = select_grounded_hits(hits)

            if not grounded_hits:
                logger.info("Chat returning insufficient evidence: query_preview=%s", query[:60])
                return {
                    "answer": INSUFFICIENT_EVIDENCE,
                    "citations": [],
                    "retrieved_count": 0,
                }

            reranked_hits = self.reranker.rerank(query=query, hits=grounded_hits)
            compressed_hits = self.compressor.compress(query=query, hits=reranked_hits)
            context = build_context(compressed_hits)
            logger.debug(
                "Chat context assembled: query_preview=%s grounded=%d reranked=%d compressed=%d context_chars=%d",
                query[:60],
                len(grounded_hits),
                len(reranked_hits),
                len(compressed_hits),
                len(context),
            )
            answer = self.llm.generate(query=query, evidence=context)
            citations = [build_citation(hit) for hit in compressed_hits]

            logger.info(
                "Chat completed: query_preview=%s grounded=%d reranked=%d compressed=%d",
                query[:60], len(grounded_hits), len(reranked_hits), len(compressed_hits),
            )

            return {
                "answer": answer,
                "citations": citations,
                "retrieved_count": len(compressed_hits),
            }

        except Exception as exc:
            logger.exception("Chat failed: query_preview=%s", query[:60])
            raise ChatError(detail=f"Chat generation failed: {exc}") from exc
