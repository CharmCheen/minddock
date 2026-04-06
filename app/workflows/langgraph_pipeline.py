"""LangGraph workflows for lightweight RAG orchestration."""

from __future__ import annotations

from collections import defaultdict
from typing import TypedDict

try:
    from langgraph.graph import END, START, StateGraph
except ModuleNotFoundError:  # pragma: no cover - optional dependency fallback
    END = "__end__"
    START = "__start__"
    StateGraph = None

from app.rag.retrieval_models import CitationRecord, ContextBlock, GroundedSelectionResult, RetrievalFilters, RetrievedChunk
from app.services.grounded_generation import build_citation, build_context, select_grounded_hits
from app.services.search_service import SearchService
from app.services.service_models import DocumentEvidenceGroup, RetrievalPreparationResult


class RetrievalWorkflowState(TypedDict, total=False):
    """Shared state for retrieval-oriented workflows."""

    query: str
    top_k: int
    filters: RetrievalFilters | None
    hits: list[RetrievedChunk]
    grounded_hits: list[RetrievedChunk]
    context: ContextBlock
    citations: list[CitationRecord]
    grouped_hits: list[DocumentEvidenceGroup]


class RetrievalWorkflow:
    """LangGraph workflow that prepares grounded evidence for service-layer chains."""

    def __init__(self, search_service: SearchService | None = None) -> None:
        self._search_service = search_service or SearchService()

    def retrieve(self, state: RetrievalWorkflowState) -> RetrievalWorkflowState:
        hits = self._search_service.retrieve(
            query=state["query"],
            top_k=state.get("top_k", 5),
            filters=state.get("filters"),
        )
        return {"hits": hits}

    def ground(self, state: RetrievalWorkflowState) -> RetrievalWorkflowState:
        grounded_selection: GroundedSelectionResult = select_grounded_hits(state.get("hits", []))
        return {"grounded_hits": grounded_selection.hits}

    def prepare_context(self, state: RetrievalWorkflowState) -> RetrievalWorkflowState:
        grounded_hits = state.get("grounded_hits", [])
        return {
            "context": build_context(grounded_hits),
            "citations": [build_citation(hit) for hit in grounded_hits],
        }

    def group_by_document(self, state: RetrievalWorkflowState) -> RetrievalWorkflowState:
        grouped: dict[str, list[RetrievedChunk]] = defaultdict(list)
        for hit in state.get("grounded_hits", []):
            grouped[hit.doc_id].append(hit)

        grouped_hits: list[DocumentEvidenceGroup] = []
        for doc_id, hits in grouped.items():
            grouped_hits.append(
                DocumentEvidenceGroup(
                    doc_id=doc_id,
                    hits=hits,
                    citation=build_citation(hits[0]),
                    context=build_context(hits),
                )
            )
        return {"grouped_hits": grouped_hits}


def build_retrieval_graph(search_service: SearchService | None = None):
    """Compile a retrieval/context-prep graph."""

    workflow = RetrievalWorkflow(search_service=search_service)
    if StateGraph is None:
        class _SequentialGraph:
            def invoke(self, state):
                state = {**state, **workflow.retrieve(state)}
                state = {**state, **workflow.ground(state)}
                state = {**state, **workflow.prepare_context(state)}
                state = {**state, **workflow.group_by_document(state)}
                return state

        return _SequentialGraph()

    graph = StateGraph(RetrievalWorkflowState)
    graph.add_node("retrieve", workflow.retrieve)
    graph.add_node("ground", workflow.ground)
    graph.add_node("prepare_context", workflow.prepare_context)
    graph.add_node("group_by_document", workflow.group_by_document)
    graph.add_edge(START, "retrieve")
    graph.add_edge("retrieve", "ground")
    graph.add_edge("ground", "prepare_context")
    graph.add_edge("prepare_context", "group_by_document")
    graph.add_edge("group_by_document", END)
    return graph.compile()


def run_retrieval_workflow(
    *,
    query: str,
    top_k: int,
    filters: RetrievalFilters | None = None,
    search_service: SearchService | None = None,
) -> RetrievalPreparationResult:
    """Invoke the retrieval graph and return its prepared result."""

    graph = build_retrieval_graph(search_service=search_service)
    state = graph.invoke({"query": query, "top_k": top_k, "filters": filters})
    return RetrievalPreparationResult(
        hits=state.get("hits", []),
        grounded_hits=state.get("grounded_hits", []),
        context=state.get("context", build_context([])),
        citations=state.get("citations", []),
        grouped_hits=state.get("grouped_hits", []),
    )
