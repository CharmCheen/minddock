"""Unified retrieval pipeline: retrieve → rerank → compress, backed by LangGraph.

This module provides a shared pipeline used by all task types (chat/summarize/compare).
It formalizes the common retrieval postprocess chain as a LangGraph with proper
step-level observability, replacing the previous pattern where each service
independently called search_service.retrieve / reranker.rerank / compressor.compress.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

try:
    from langgraph.graph import END, START, StateGraph
except ModuleNotFoundError:  # pragma: no cover - optional dependency fallback
    END = "__end__"
    START = "__start__"
    StateGraph = None

from app.rag.postprocess import Compressor, Reranker, get_compressor, get_reranker
from app.rag.retrieval_models import RetrievedChunk
from app.services.search_service import SearchService

if TYPE_CHECKING:
    pass


class UnifiedWorkflowState(TypedDict, total=False):
    """Shared state for the unified retrieval pipeline.

    Fields are populated progressively by each node:
      - query, top_k, filters: set at invocation time
      - hits: after retrieve node
      - reranked_hits: after rerank node
      - compressed_hits: after compress node
    """

    query: str
    top_k: int
    filters: dict | None
    hits: list[RetrievedChunk]
    reranked_hits: list[RetrievedChunk]
    compressed_hits: list[RetrievedChunk]


class RetrievalPipeline:
    """Unified retrieve → rerank → compress pipeline.

    Wraps the common post-retrieval chain so it can be invoked from a single
    entry point and observed step-by-step via LangGraph events.

    All three task types (CHAT, SUMMARIZE, COMPARE) share this same chain;
    only the generation step after compression is task-specific and stays in
    the individual services.
    """

    def __init__(
        self,
        search_service: SearchService | None = None,
        reranker: Reranker | None = None,
        compressor: Compressor | None = None,
    ) -> None:
        self._search_service = search_service or SearchService()
        self._reranker = reranker or get_reranker()
        self._compressor = compressor or get_compressor()

    # -------------------------------------------------------------------------
    # LangGraph node implementations
    # -------------------------------------------------------------------------

    def retrieve(self, state: UnifiedWorkflowState) -> UnifiedWorkflowState:
        """Fetch initial retrieval hits from the vector store."""
        hits = self._search_service.retrieve(
            query=state["query"],
            top_k=state.get("top_k", 5),
            filters=state.get("filters"),
        )
        return {"hits": hits}

    def rerank(self, state: UnifiedWorkflowState) -> UnifiedWorkflowState:
        """Apply heuristic reranking to retrieval hits."""
        hits = state.get("hits", [])
        if not hits:
            return {"reranked_hits": []}
        reranked = self._reranker.rerank(query=state["query"], hits=hits)
        return {"reranked_hits": reranked}

    def compress(self, state: UnifiedWorkflowState) -> UnifiedWorkflowState:
        """Apply context compression (sentence-level trimming)."""
        reranked = state.get("reranked_hits", [])
        if not reranked:
            return {"compressed_hits": []}
        compressed = self._compressor.compress(query=state["query"], hits=reranked)
        return {"compressed_hits": compressed}

    # -------------------------------------------------------------------------
    # Graph construction
    # -------------------------------------------------------------------------

    def build_graph(self):
        """Build the LangGraph pipeline (retrieve → rerank → compress → END).

        Returns a compiled graph, or a ``_SequentialGraph`` fallback when
        langgraph is not installed.
        """
        if StateGraph is None:
            # Minimal sequential fallback — same node functions, no graph structure
            class _SequentialGraph:
                def invoke(self, state: UnifiedWorkflowState) -> UnifiedWorkflowState:
                    state = {**state, **self._node("retrieve", state)}
                    state = {**state, **self._node("rerank", state)}
                    state = {**state, **self._node("compress", state)}
                    return state

                def _node(self, name: str, state: UnifiedWorkflowState):
                    if name == "retrieve":
                        return RetrievalPipeline._retrieve(self, state)
                    if name == "rerank":
                        return RetrievalPipeline._rerank(self, state)
                    if name == "compress":
                        return RetrievalPipeline._compress(self, state)
                    return {}

            instance = _SequentialGraph()
            instance._retrieve = self.retrieve
            instance._rerank = self.rerank
            instance._compress = self.compress
            return instance

        graph = StateGraph(UnifiedWorkflowState)
        graph.add_node("retrieve", self.retrieve)
        graph.add_node("rerank", self.rerank)
        graph.add_node("compress", self.compress)
        graph.add_edge(START, "retrieve")
        graph.add_edge("retrieve", "rerank")
        graph.add_edge("rerank", "compress")
        graph.add_edge("compress", END)
        return graph.compile()

    # -------------------------------------------------------------------------
    # Convenience entry point
    # -------------------------------------------------------------------------

    def run(self, *, query: str, top_k: int = 5, filters=None) -> UnifiedWorkflowState:
        """Run the full pipeline and return the final state dict.

        Returns the full state dict including hits / reranked_hits / compressed_hits
        so callers can pass the results downstream without re-running the chain.
        """
        compiled = self.build_graph()
        return compiled.invoke({
            "query": query,
            "top_k": top_k,
            "filters": filters,
            "hits": [],
            "reranked_hits": [],
            "compressed_hits": [],
        })


def build_unified_graph(
    search_service: SearchService | None = None,
    reranker: Reranker | None = None,
    compressor: Compressor | None = None,
):
    """Factory: build a compiled LangGraph backed by RetrievalPipeline nodes.

    Returns a ``_SequentialGraph`` fallback when langgraph is unavailable,
    exposing the same ``invoke(state) → state`` interface.
    """
    pipeline = RetrievalPipeline(
        search_service=search_service,
        reranker=reranker,
        compressor=compressor,
    )
    return pipeline.build_graph()
