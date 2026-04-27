"""Unified retrieval pipeline: retrieve → rerank → compress, backed by LangGraph.

This module provides a shared pipeline used by all task types (chat/summarize/compare).
It formalizes the common post-retrieval chain as a LangGraph with proper
step-level observability, replacing the previous pattern where each service
independently called search_service.retrieve / reranker.rerank / compressor.compress.
"""

from __future__ import annotations

import re
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
      - quality_ok, quality_reasons, low_confidence, reflection: after quality_check
      - original_query, expanded_query, retry_count, max_retries: loop control
      - task_type: passed from orchestrator for quality rules
    """

    query: str
    top_k: int
    filters: dict | None
    hits: list[RetrievedChunk]
    reranked_hits: list[RetrievedChunk]
    compressed_hits: list[RetrievedChunk]

    # Quality / reflection
    quality_ok: bool
    quality_reasons: list[str]
    low_confidence: bool
    reflection: dict

    # Retry control
    original_query: str
    expanded_query: str
    retry_count: int
    max_retries: int
    task_type: str


# Instruction words stripped during query expansion for retry.
_INSTRUCTION_WORDS_CN = frozenset(
    {
        "总结",
        "概括",
        "归纳",
        "摘要",
        "提炼",
        "梳理",
        "比较",
        "对比",
        "区别",
        "差异",
        "异同",
    }
)
_INSTRUCTION_WORDS_EN = frozenset(
    {
        "summarize",
        "summary",
        "recap",
        "outline",
        "compare",
        "comparison",
        "difference",
        "differences",
        "contrast",
        "versus",
        "vs",
    }
)


def _strip_instruction_words(query: str) -> str:
    """Remove task-style instruction words from the query for retry expansion."""
    result = query
    for word in _INSTRUCTION_WORDS_CN:
        result = result.replace(word, "")
    for word in _INSTRUCTION_WORDS_EN:
        result = re.sub(rf"\b{re.escape(word)}\b", "", result, flags=re.IGNORECASE)
    # Normalize punctuation to spaces, then collapse whitespace
    result = re.sub(r"[^\w\s]", " ", result)
    result = " ".join(result.split())
    return result


class _SequentialGraph:
    """Fallback sequential graph when LangGraph is unavailable.

    Mirrors the retrieve → rerank → compress → quality_check path with one
    bounded retry (query_expand → retrieve …) and exposes the same
    ``invoke()`` and ``stream()`` interfaces as a compiled LangGraph.
    """

    def __init__(self, pipeline: RetrievalPipeline) -> None:
        self._pipeline = pipeline

    def invoke(self, state: UnifiedWorkflowState) -> UnifiedWorkflowState:
        if state.get("original_query") is None:
            state = {**state, "original_query": state.get("query", "")}
        while True:
            state = {**state, **self._pipeline.retrieve(state)}
            state = {**state, **self._pipeline.rerank(state)}
            state = {**state, **self._pipeline.compress(state)}
            state = {**state, **self._pipeline.quality_check(state)}
            if state.get("quality_ok") or state.get("retry_count", 0) >= state.get("max_retries", 1):
                break
            state = {**state, **self._pipeline.query_expand(state)}
        return state

    def stream(self, state: UnifiedWorkflowState):
        if state.get("original_query") is None:
            state = {**state, "original_query": state.get("query", "")}
        while True:
            result = self._pipeline.retrieve(state)
            state = {**state, **result}
            yield {"retrieve": result}
            result = self._pipeline.rerank(state)
            state = {**state, **result}
            yield {"rerank": result}
            result = self._pipeline.compress(state)
            state = {**state, **result}
            yield {"compress": result}
            result = self._pipeline.quality_check(state)
            state = {**state, **result}
            yield {"quality_check": result}
            if state.get("quality_ok") or state.get("retry_count", 0) >= state.get("max_retries", 1):
                break
            result = self._pipeline.query_expand(state)
            state = {**state, **result}
            yield {"query_expand": result}


class RetrievalPipeline:
    """Unified retrieve → rerank → compress pipeline with quality reflection
    and one bounded retry.

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

    def quality_check(self, state: UnifiedWorkflowState) -> UnifiedWorkflowState:
        """Rule-based quality check after compression.

        Returns quality_ok, quality_reasons, low_confidence, and reflection.
        """
        task_type = state.get("task_type", "chat")
        hits = state.get("hits", [])
        compressed = state.get("compressed_hits", [])
        reasons: list[str] = []
        low_confidence = False
        quality_ok = True

        if not hits:
            quality_ok = False
            reasons.append("No hits retrieved")
        if not compressed:
            quality_ok = False
            reasons.append("No compressed hits")

        if task_type == "summarize":
            if len(compressed) < 2 and len(hits) > 1:
                quality_ok = False
                reasons.append("Insufficient diversity for summarize")

        # Weak retrieval: only flag when all distances are present and >= 1.5
        if hits and all(h.distance is not None and h.distance >= 1.5 for h in hits):
            low_confidence = True
            reasons.append("All retrieval distances are weak (>= 1.5)")

        reflection = {
            "attempt": state.get("retry_count", 0) + 1,
            "reasons": reasons,
            "low_confidence": low_confidence,
        }

        return {
            "quality_ok": quality_ok,
            "quality_reasons": reasons,
            "low_confidence": low_confidence,
            "reflection": reflection,
        }

    def query_expand(self, state: UnifiedWorkflowState) -> UnifiedWorkflowState:
        """Deterministic query expansion for one retry attempt.

        Strips instruction words, normalizes whitespace, and modestly increases top_k.
        """
        original_query = state.get("original_query") or state["query"]
        current_query = state["query"]
        expanded = _strip_instruction_words(current_query)
        if not expanded:
            expanded = original_query

        top_k = state.get("top_k", 5)
        retry_top_k = min(max(top_k + 3, int(top_k * 1.5)), 20)

        return {
            "original_query": original_query,
            "expanded_query": expanded,
            "query": expanded,
            "top_k": retry_top_k,
            "retry_count": state.get("retry_count", 0) + 1,
        }

    # -------------------------------------------------------------------------
    # Graph construction
    # -------------------------------------------------------------------------

    def _route_after_quality(self, state: UnifiedWorkflowState) -> str:
        if state.get("quality_ok"):
            return END
        if state.get("retry_count", 0) < state.get("max_retries", 1):
            return "query_expand"
        return END

    def build_graph(self):
        """Build the LangGraph pipeline with conditional retry.

        retrieve → rerank → compress → quality_check
          ├─ quality_ok ──→ END
          └─ retry ───────→ query_expand → retrieve …

        Returns a compiled graph, or a ``_SequentialGraph`` fallback when
        langgraph is not installed.
        """
        if StateGraph is None:
            return _SequentialGraph(self)

        graph = StateGraph(UnifiedWorkflowState)
        graph.add_node("retrieve", self.retrieve)
        graph.add_node("rerank", self.rerank)
        graph.add_node("compress", self.compress)
        graph.add_node("quality_check", self.quality_check)
        graph.add_node("query_expand", self.query_expand)
        graph.add_edge(START, "retrieve")
        graph.add_edge("retrieve", "rerank")
        graph.add_edge("rerank", "compress")
        graph.add_edge("compress", "quality_check")
        graph.add_conditional_edges(
            "quality_check",
            self._route_after_quality,
            {END: END, "query_expand": "query_expand"},
        )
        graph.add_edge("query_expand", "retrieve")
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
        task_type: str = "chat",
        event_emitter: Callable[[RetrievalPipelineProgressPayload], None] | None = None,
    ) -> UnifiedWorkflowState:
        """Run the full pipeline and return the final state dict.

        Args:
            event_emitter: if provided, called after each pipeline stage with
                a ``RetrievalPipelineProgressPayload`` describing the completed stage.
                This allows the caller to emit trace events without duplicating the
                pipeline execution logic.
            task_type: one of ``chat``, ``summarize``, ``compare``, ``search``.
                Used by the quality check node to apply task-specific rules.
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
            "task_type": task_type,
            "hits": [],
            "reranked_hits": [],
            "compressed_hits": [],
            "retry_count": 0,
            "max_retries": 1,
            "quality_ok": True,
            "quality_reasons": [],
            "low_confidence": False,
            "reflection": {},
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
