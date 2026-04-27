"""Unified retrieval pipeline: retrieve → rerank → compress, backed by LangGraph.

This module provides a shared pipeline used by all task types (chat/summarize/compare).
It formalizes the common retrieval postprocess chain as a LangGraph with proper
step-level observability, replacing the previous pattern where each service
independently called search_service.retrieve / reranker.rerank / compressor.compress.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Callable, TypedDict

try:
    from langgraph.graph import END, START, StateGraph
except ModuleNotFoundError:  # pragma: no cover - optional dependency fallback
    END = "__end__"
    START = "__start__"
    StateGraph = None

from app.rag.postprocess import Compressor, Reranker, get_compressor, get_reranker
from app.rag.retrieval_models import RetrievedChunk
from app.services.search_service import SearchService
from app.application.events import RetrievalPipelineCompletedPayload, RetrievalPipelineProgressPayload


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


class _SequentialGraph:
    """Fallback sequential graph when LangGraph is unavailable.

    Mirrors the linear retrieve → rerank → compress path and exposes the
    same ``invoke()`` and ``stream()`` interfaces as a compiled LangGraph.
    """

    def __init__(self, pipeline: RetrievalPipeline) -> None:
        self._pipeline = pipeline

    def invoke(self, state: UnifiedWorkflowState) -> UnifiedWorkflowState:
        state = {**state, **self._pipeline.retrieve(state)}
        state = {**state, **self._pipeline.rerank(state)}
        state = {**state, **self._pipeline.compress(state)}
        return state

    def stream(self, state: UnifiedWorkflowState):
        result = self._pipeline.retrieve(state)
        state = {**state, **result}
        yield {"retrieve": result}
        result = self._pipeline.rerank(state)
        state = {**state, **result}
        yield {"rerank": result}
        result = self._pipeline.compress(state)
        state = {**state, **result}
        yield {"compress": result}


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
            return _SequentialGraph(self)

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

    def run(
        self,
        *,
        query: str,
        top_k: int = 5,
        filters=None,
        event_emitter: Callable[[RetrievalPipelineProgressPayload], None] | None = None,
    ) -> UnifiedWorkflowState:
        """Run the full pipeline and return the final state dict.

        Args:
            event_emitter: if provided, called after each pipeline stage with
                a ``RetrievalPipelineProgressPayload`` describing the completed stage.
                This allows the caller to emit trace events without duplicating the
                pipeline execution logic.
        """
        pipeline_started = time.perf_counter()

        if event_emitter is not None:
            event_emitter(
                RetrievalPipelineProgressPayload(stage="retrieval_started")
            )

        compiled = self.build_graph()
        state: UnifiedWorkflowState = {
            "query": query,
            "top_k": top_k,
            "filters": filters,
            "hits": [],
            "reranked_hits": [],
            "compressed_hits": [],
        }

        if event_emitter is not None:
            for update in compiled.stream(state):
                for node_name, node_output in update.items():
                    state = {**state, **node_output}
                    if node_name == "retrieve":
                        event_emitter(
                            RetrievalPipelineProgressPayload(
                                stage="retrieval_completed",
                                retrieved_hits=len(state.get("hits", [])),
                            )
                        )
                    elif node_name == "rerank":
                        event_emitter(
                            RetrievalPipelineProgressPayload(
                                stage="rerank_completed",
                                retrieved_hits=len(state.get("hits", [])),
                                reranked_hits=len(state.get("reranked_hits", [])),
                            )
                        )
                    elif node_name == "compress":
                        event_emitter(
                            RetrievalPipelineProgressPayload(
                                stage="compress_completed",
                                retrieved_hits=len(state.get("hits", [])),
                                reranked_hits=len(state.get("reranked_hits", [])),
                                compressed_hits=len(state.get("compressed_hits", [])),
                            )
                        )
            total_ms = round((time.perf_counter() - pipeline_started) * 1000, 2)
            event_emitter(
                RetrievalPipelineCompletedPayload(
                    retrieved_hits=len(state.get("hits", [])),
                    reranked_hits=len(state.get("reranked_hits", [])),
                    compressed_hits=len(state.get("compressed_hits", [])),
                    total_ms=total_ms,
                )
            )
            return state

        return compiled.invoke(state)


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
