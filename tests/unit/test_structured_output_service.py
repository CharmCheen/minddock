"""Unit tests for structured grounded outputs."""

from app.services.structured_output_service import StructuredOutputService


def test_structured_output_service_renders_mermaid_mindmap() -> None:
    service = StructuredOutputService()
    mermaid = service.render_mermaid(
        topic="MindDock storage",
        evidence=[
            {
                "chunk_id": "c1",
                "source": "example.md",
                "ref": "example > Storage",
                "text": "MindDock stores document chunks and metadata in local Chroma storage.",
            }
        ],
    )

    assert mermaid.startswith("mindmap")
    assert 'root["MindDock storage"]' in mermaid
    assert 'e1["example > Storage"]' in mermaid
