"""Application service for grounded chat responses."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.llm.factory import get_llm_provider
from app.llm.mock import INSUFFICIENT_EVIDENCE
from app.rag.postprocess import Compressor, Reranker, get_compressor, get_reranker
from app.services.search_service import SearchService
from ports.llm import LLMProvider

SNIPPET_LIMIT = 120
MAX_EVIDENCE_DISTANCE = 1.5


@dataclass
class ChatService:
    """Build a minimal retrieve-then-generate pipeline with citations."""

    search_service: SearchService = field(default_factory=SearchService)
    reranker: Reranker = field(default_factory=get_reranker)
    compressor: Compressor = field(default_factory=get_compressor)
    llm: LLMProvider = field(default_factory=get_llm_provider)

    def chat(self, query: str, top_k: int) -> dict[str, object]:
        hits = self.search_service.retrieve(query=query, top_k=top_k)
        grounded_hits = [hit for hit in hits if self._is_grounded(hit)]
        if not grounded_hits:
            return {
                "answer": INSUFFICIENT_EVIDENCE,
                "citations": [],
                "retrieved_count": 0,
            }

        reranked_hits = self.reranker.rerank(query=query, hits=grounded_hits)
        compressed_hits = self.compressor.compress(query=query, hits=reranked_hits)
        context = self._assemble_context(compressed_hits)
        answer = self.llm.generate(query=query, evidence=context)
        citations = [self._build_citation(hit) for hit in compressed_hits]
        return {
            "answer": answer,
            "citations": citations,
            "retrieved_count": len(compressed_hits),
        }

    def _assemble_context(self, hits: list[dict[str, object]]) -> list[dict[str, object]]:
        context = []
        for hit in hits:
            context.append(
                {
                    "chunk_id": hit["chunk_id"],
                    "source": hit["source"],
                    "text": hit["text"],
                }
            )
        return context

    def _build_citation(self, hit: list[dict[str, object]] | dict[str, object]) -> dict[str, str]:
        text = str(hit["text"]).strip().replace("\n", " ")
        return {
            "doc_id": str(hit["doc_id"]),
            "chunk_id": str(hit["chunk_id"]),
            "source": str(hit["source"]),
            "snippet": text[:SNIPPET_LIMIT],
        }

    def _is_grounded(self, hit: dict[str, object]) -> bool:
        distance = hit.get("distance")
        if distance is None:
            return True
        return float(distance) < MAX_EVIDENCE_DISTANCE
