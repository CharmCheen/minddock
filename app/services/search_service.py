"""Application service for semantic vector search."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from app.core.config import get_settings
from app.core.exceptions import SearchError
from app.rag.hybrid_retrieval import HybridRetrievalService, get_hybrid_retrieval_service
from app.rag.retrieval_models import RetrievalFilters, RetrievedChunk, SearchHitRecord, SearchResult
from app.services.service_models import RetrievalStats, SearchServiceResult, ServiceIssue, UseCaseMetadata, UseCaseTiming
from app.rag.vectorstore import get_vectorstore
from app.services.grounded_generation import build_citation

logger = logging.getLogger(__name__)


@dataclass
class SearchService:
    """Bridge API requests to vector retrieval with formal hit/citation models."""

    vectorstore: object = field(default_factory=get_vectorstore)
    hybrid_service: HybridRetrievalService | None = None

    def _get_hybrid_service(self) -> HybridRetrievalService:
        if self.hybrid_service is None:
            self.hybrid_service = get_hybrid_retrieval_service(
                vectorstore=self.vectorstore,
            )
        return self.hybrid_service

    def retrieve(self, query: str, top_k: int, filters: RetrievalFilters | None = None) -> list[RetrievedChunk]:
        """Retrieve normalized hits from the vector store."""

        settings = get_settings()
        if settings.hybrid_retrieval_enabled:
            return self._get_hybrid_service().retrieve(query=query, top_k=top_k, filters=filters)

        hits = self.vectorstore.search_by_text(query=query, top_k=top_k, filters=filters)
        logger.debug(
            "Retrieval completed: query_preview=%s top_k=%d hits=%d filters=%s",
            query[:60],
            top_k,
            len(hits),
            filters,
        )
        return hits

    def retrieve_structured_reference_candidates(
        self,
        query: str,
        top_k: int,
        filters: RetrievalFilters | None = None,
    ) -> list[RetrievedChunk]:
        """Retrieve a small lexical candidate set for explicit table/figure references."""

        if top_k <= 0:
            return []
        try:
            return self._get_hybrid_service().retrieve_lexical_candidates(
                query=query,
                top_k=top_k,
                filters=filters,
            )
        except Exception:
            logger.exception("Structured reference lexical retrieval failed: query_preview=%s", query[:60])
            return []

    def search(self, query: str, top_k: int, filters: RetrievalFilters | None = None) -> SearchServiceResult:
        """Execute search and return a formal search result."""

        try:
            started = time.perf_counter()
            hits = self.retrieve(query=query, top_k=top_k, filters=filters)
            search_hits = [SearchHitRecord(chunk=hit, citation=build_citation(hit)) for hit in hits]
            elapsed_ms = round((time.perf_counter() - started) * 1000, 2)

            logger.info(
                "Search response built: query_preview=%s hits=%d",
                query[:60],
                len(search_hits),
            )
            return SearchServiceResult(
                search_result=SearchResult(query=query, top_k=top_k, hits=search_hits),
                metadata=UseCaseMetadata(
                    retrieved_count=len(search_hits),
                    empty_result=not search_hits,
                    warnings=("No search hits matched the query.",) if not search_hits else (),
                    issues=(
                        ServiceIssue(
                            code="empty_result",
                            message="No search hits matched the query.",
                            severity="info",
                        ),
                    )
                    if not search_hits
                    else (),
                    timing=UseCaseTiming(total_ms=elapsed_ms, retrieval_ms=elapsed_ms),
                    filter_applied=filters is not None,
                    retrieval_stats=RetrievalStats(
                        retrieved_hits=len(hits),
                        returned_hits=len(search_hits),
                    ),
                ),
            )
        except Exception as exc:
            logger.exception("Search failed: query_preview=%s", query[:60])
            raise SearchError(detail=f"Search failed: {exc}") from exc
