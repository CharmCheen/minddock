"""Unit tests for the review workbench MVP (PRD FR-7)."""

from __future__ import annotations

import json

from app.rag.retrieval_models import RetrievedChunk
from app.services.review_workbench_service import (
    ReviewWorkbenchRequest,
    run_review_workbench,
)


class _FakeSearchService:
    """Returns one grounded hit per known source; empty for unknown ones."""

    def __init__(self, corpus: dict[str, str]):
        self._corpus = corpus

    def retrieve(self, *, query: str, top_k: int, filters=None):
        sources = getattr(filters, "sources", ()) if filters is not None else ()
        if not sources:
            return []
        source = sources[0]
        text = self._corpus.get(source)
        if not text:
            return []
        doc_id = f"doc-{abs(hash(source)) % 10**8}"
        return [
            RetrievedChunk.from_raw(
                text=text,
                metadata={
                    "doc_id": doc_id,
                    "chunk_id": f"{doc_id}:0",
                    "source": source,
                    "title": source,
                    "section": "Overview",
                    "page": 1,
                },
                distance=0.4,
            )
        ]


def _service_with_sources() -> tuple[_FakeSearchService, dict[str, str]]:
    corpus = {
        "docs/a.md": "Retrieval augmented generation grounds answers using vector search. Section-aware splitting keeps headings.",
        "docs/b.md": "The pipeline embeds chunks with sentence-transformers and stores them in Chroma.",
        "docs/c.md": "Citations carry source, section, and page metadata for verification.",
    }
    return _FakeSearchService(corpus), corpus


class TestReviewWorkbench:
    def test_three_sources_produce_table_and_citations(self):
        service, corpus = _service_with_sources()
        result = run_review_workbench(
            ReviewWorkbenchRequest(topic="How do these documents describe the RAG pipeline?", sources=("docs/a.md", "docs/b.md", "docs/c.md")),
            search_service=service,
        )
        assert result.schema_name == "review.v1"
        payload = result.payload
        assert len(payload["covered_sources"]) == 3
        assert len(payload["table"]) >= 1
        row = payload["table"][0]
        assert row["dimension"]
        assert len(row["cells"]) >= 2
        cell = next(c for c in row["cells"] if c["citation"] is not None)
        assert 1 <= cell["citation"] <= len(result.citations)
        assert len(result.citations) == 3
        # Every citation index in cells maps to a real citation.
        refs = {i + 1 for i in range(len(result.citations))}
        for row in payload["table"]:
            for cell in row["cells"]:
                if cell["citation"] is not None:
                    assert cell["citation"] in refs

    def test_honest_signals_without_runtime_never_green(self):
        """PRD v1.2 D-1: skipped LLM layers must degrade visibly, never green."""
        service, _ = _service_with_sources()
        result = run_review_workbench(
            ReviewWorkbenchRequest(topic="pipeline", sources=("docs/a.md", "docs/b.md")),
            search_service=service,
        )
        trace = result.metadata.workflow_trace
        assert trace["synthesis_llm_layer"] == "skipped_no_runtime"
        assert trace["verification_layers"]["llm"] == "skipped_no_runtime"
        assert trace["quality_ok"] is False
        assert trace["low_confidence"] is True
        assert "llm_layers_degraded" in trace["quality_reasons"]
        assert any(w.startswith("self_check_llm_skipped") for w in trace["trace_warnings"])
        assert any(w == "review_llm_fallback_extractive" for w in result.metadata.warnings)
        assert result.metadata.support_status == "partially_supported"

    def test_full_llm_layers_earn_supported(self):
        class _DualRuntime:
            runtime_name = "fake-dual"

            def invoke(self, *, prompt, inputs, fallback_query, fallback_evidence, llm_override=None):
                if "verdict" in prompt and "cited evidence" in prompt.lower():
                    return json.dumps([{"index": i + 1, "verdict": "supported", "reason": "match"} for i in range(4)])
                return json.dumps(
                    {
                        "overview": "Docs align on grounding.",
                        "table": [
                            {
                                "dimension": "Grounding",
                                "cells": [
                                    {"source": "docs/a.md", "point": "Vector search grounds answers.", "citation": 1},
                                    {"source": "docs/b.md", "point": "Chroma stores embeddings.", "citation": 2},
                                ],
                            }
                        ],
                        "takeaways": ["Aligned."],
                    }
                )

        service, _ = _service_with_sources()
        result = run_review_workbench(
            ReviewWorkbenchRequest(topic="grounding", sources=("docs/a.md", "docs/b.md")),
            search_service=service,
            runtime=_DualRuntime(),
        )
        trace = result.metadata.workflow_trace
        assert trace["synthesis_llm_layer"] == "completed"
        assert trace["verification_layers"]["llm"] == "completed"
        assert result.metadata.support_status == "supported"

    def test_insufficient_when_only_one_source_has_evidence(self):
        service, corpus = _service_with_sources()
        result = run_review_workbench(
            ReviewWorkbenchRequest(topic="anything", sources=("docs/missing1.md", "docs/missing2.md")),
            search_service=service,
        )
        assert result.metadata.insufficient_evidence is True
        assert result.payload.get("insufficient_evidence") is True
        assert result.citations == []
        trace = result.metadata.workflow_trace
        assert trace["quality_ok"] is False
        assert trace["low_confidence"] is True

    def test_too_few_sources_is_rejected(self):
        service, _ = _service_with_sources()
        result = run_review_workbench(
            ReviewWorkbenchRequest(topic="topic", sources=("only-one.md",)),
            search_service=service,
        )
        assert result.metadata.insufficient_evidence is True

    def test_llm_synthesis_parsed_and_marked(self):
        class _FakeRuntime:
            runtime_name = "fake"

            def invoke(self, *, prompt, inputs, fallback_query, fallback_evidence, llm_override=None):
                if "verdict" in prompt and "cited evidence" in prompt.lower():
                    # Verification layer fails in this scenario; synthesis still works.
                    raise ValueError("no verdicts here")
                return json.dumps(
                    {
                        "overview": "All three docs describe grounding.",
                        "table": [
                            {
                                "dimension": "Grounding",
                                "cells": [
                                    {"source": "docs/a.md", "point": "Vector search grounds answers.", "citation": 1},
                                    {"source": "docs/b.md", "point": "Chroma stores embeddings.", "citation": 2},
                                ],
                            }
                        ],
                        "takeaways": ["Docs agree on grounding."],
                    }
                )

        service, _ = _service_with_sources()
        result = run_review_workbench(
            ReviewWorkbenchRequest(topic="grounding", sources=("docs/a.md", "docs/b.md")),
            search_service=service,
            runtime=_FakeRuntime(),
        )
        assert result.payload["llm_layer"] == "completed"
        assert result.payload["overview"].startswith("All three")
        assert result.payload["table"][0]["cells"][0]["citation"] == 1

    def test_llm_failure_degrades_to_extractive(self):
        class _BrokenRuntime:
            runtime_name = "broken"

            def invoke(self, **kwargs):
                raise RuntimeError("boom")

        service, _ = _service_with_sources()
        result = run_review_workbench(
            ReviewWorkbenchRequest(topic="grounding", sources=("docs/a.md", "docs/c.md")),
            search_service=service,
            runtime=_BrokenRuntime(),
        )
        assert result.payload["llm_layer"].startswith("failed:")
        assert any(w.startswith("review_llm_fallback") for w in result.metadata.warnings)

    def test_markdown_contains_citation_markers(self):
        service, _ = _service_with_sources()
        result = run_review_workbench(
            ReviewWorkbenchRequest(topic="pipeline", sources=("docs/a.md", "docs/b.md")),
            search_service=service,
        )
        assert result.answer_markdown.startswith("# Review:")
        assert "[1]" in result.answer_markdown or "[2]" in result.answer_markdown
