from pathlib import Path

from app.rag.ingest import build_document_payload


def test_build_document_payload_includes_traceable_metadata(tmp_path: Path) -> None:
    kb_dir = tmp_path / "knowledge_base"
    kb_dir.mkdir()
    doc_path = kb_dir / "notes.md"
    doc_path.write_text("# Storage\nMindDock stores chunks in Chroma.\n", encoding="utf-8")

    payload = build_document_payload(path=doc_path, kb_dir=kb_dir)

    assert payload["doc_id"]
    metadata = payload["metadatas"][0]
    assert metadata["source"] == "notes.md"
    assert metadata["source_path"] == "notes.md"
    assert metadata["title"] == "notes"
    assert metadata["section"] == "Storage"
    assert metadata["location"] == "Storage"
    assert metadata["ref"] == "notes > Storage"
