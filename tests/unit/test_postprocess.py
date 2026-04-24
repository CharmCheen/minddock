"""Unit tests for reranking and compression."""

from app.rag.postprocess import HeuristicReranker, TrimmingCompressor
from app.rag.retrieval_models import RetrievedChunk
from app.services.grounded_generation import build_citation


def test_heuristic_reranker_changes_hit_order() -> None:
    reranker = HeuristicReranker()
    hits = [
        RetrievedChunk(
            text="General notes about unrelated UI polish.",
            doc_id="d1",
            chunk_id="c1",
            source="ui.md",
            title="UI",
            section="Design",
            location="Design",
            ref="UI > Design",
            distance=0.05,
        ),
        RetrievedChunk(
            text="MindDock stores document chunks and metadata in local Chroma storage.",
            doc_id="d2",
            chunk_id="c2",
            source="storage.md",
            title="Storage",
            section="Persistence",
            location="Persistence",
            ref="Storage > Persistence",
            distance=0.4,
        ),
    ]

    reranked = reranker.rerank("where are chunks stored", hits)

    assert reranked[0].chunk_id == "c2"
    assert reranked[0].rerank_score >= reranked[1].rerank_score


def test_heuristic_reranker_boosts_explicit_section_title_match() -> None:
    reranker = HeuristicReranker()
    hits = [
        RetrievedChunk(
            text="Milvus is a full-fledged vector data management system for similarity search.",
            doc_id="milvus",
            chunk_id="intro",
            source="milvus.pdf",
            section="INTRODUCTION",
            distance=0.05,
        ),
        RetrievedChunk(
            text="In this section, we present an overview of Milvus architecture and its components.",
            doc_id="milvus",
            chunk_id="system-design",
            source="milvus.pdf",
            section="SYSTEM DESIGN",
            distance=0.4,
        ),
    ]

    reranked = reranker.rerank("What does the SYSTEM DESIGN section describe?", hits)

    assert reranked[0].chunk_id == "system-design"
    assert reranked[0].rerank_score >= reranked[1].rerank_score


def test_heuristic_reranker_does_not_boost_unmentioned_section_title() -> None:
    reranker = HeuristicReranker()
    hits = [
        RetrievedChunk(
            text="Milvus is an open-source vector database for similarity search.",
            doc_id="milvus",
            chunk_id="intro",
            source="milvus.pdf",
            section="INTRODUCTION",
            distance=0.05,
        ),
        RetrievedChunk(
            text="The system design includes query processing and heterogeneous computing.",
            doc_id="milvus",
            chunk_id="system-design",
            source="milvus.pdf",
            section="SYSTEM DESIGN",
            distance=0.4,
        ),
    ]

    reranked = reranker.rerank("What is Milvus?", hits)

    assert reranked[0].chunk_id == "intro"


def test_heuristic_reranker_is_cautious_with_common_sections() -> None:
    reranker = HeuristicReranker()
    hits = [
        RetrievedChunk(
            text="The paper contributes a distributed vector data management system.",
            doc_id="milvus",
            chunk_id="contribution",
            source="milvus.pdf",
            section="SYSTEM DESIGN",
            distance=0.12,
        ),
        RetrievedChunk(
            text="The introduction describes the motivation and background.",
            doc_id="milvus",
            chunk_id="introduction",
            source="milvus.pdf",
            section="INTRODUCTION",
            distance=0.3,
        ),
    ]

    reranked = reranker.rerank("What is the main contribution of the paper?", hits)

    assert reranked[0].chunk_id == "contribution"


def test_trimming_compressor_shortens_text_and_preserves_citation_text() -> None:
    compressor = TrimmingCompressor()
    hits = [
        RetrievedChunk(
            text=(
                "MindDock stores chunks in Chroma. "
                "This sentence is relevant to storage. "
                "Unrelated sentence about weather and coffee."
            ),
            doc_id="d1",
            chunk_id="c1",
            source="storage.md",
            title="Storage",
            section="Persistence",
            location="Persistence",
            ref="Storage > Persistence",
            distance=0.2,
        )
    ] * 6

    compressed = compressor.compress("where are chunks stored", hits)
    citation = build_citation(compressed[0])

    assert len(compressed) == 4
    assert compressed[0].compression_applied is True
    assert len(compressed[0].text) < len(hits[0].text)
    assert compressed[0].original_text == hits[0].text
    assert citation.snippet.startswith("MindDock stores chunks in Chroma.")
