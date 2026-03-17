from app.llm.mock import INSUFFICIENT_EVIDENCE, MockLLM


def test_mock_llm_returns_readable_grounded_answer() -> None:
    llm = MockLLM()

    answer = llm.generate(
        query="where is data stored",
        evidence=[
            {
                "chunk_id": "c1",
                "source": "kb/doc.md",
                "text": "MindDock stores chunks and metadata in local Chroma.",
            },
            {
                "chunk_id": "c2",
                "source": "kb/doc.md",
                "text": "The data directory is data/chroma by default.",
            },
        ],
    )

    assert "where is data stored" in answer
    assert "local Chroma" in answer
    assert "data/chroma" in answer


def test_mock_llm_returns_readable_summary() -> None:
    llm = MockLLM()

    summary = llm.generate(
        query="Summarize the topic using only the provided evidence.\nTopic: storage design",
        evidence=[
            {
                "chunk_id": "c1",
                "source": "kb/doc.md",
                "text": "MindDock stores chunks and metadata in local Chroma.",
            }
        ],
    )

    assert "storage design" in summary
    assert "主要反映出以下要点" in summary


def test_mock_llm_returns_insufficient_evidence_without_text() -> None:
    llm = MockLLM()

    answer = llm.generate(query="test", evidence=[])

    assert answer == INSUFFICIENT_EVIDENCE
