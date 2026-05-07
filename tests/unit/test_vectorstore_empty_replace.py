from app.rag.vectorstore import LangChainChromaStore


def test_replace_document_refuses_empty_replace_when_chunks_exist(monkeypatch) -> None:
    store = LangChainChromaStore.__new__(LangChainChromaStore)
    deleted: list[str] = []

    monkeypatch.setattr(store, "list_document_chunk_ids", lambda doc_id: [f"{doc_id}:0"])
    monkeypatch.setattr(store, "delete_ids", lambda ids: deleted.extend(ids) or len(ids))

    try:
        store.replace_document(
            doc_id="doc-1",
            ids=[],
            documents=[],
            metadatas=[],
            embeddings=[],
        )
    except ValueError as exc:
        assert "Refusing empty replacement" in str(exc)
    else:
        raise AssertionError("empty replacement should be refused by default")

    assert deleted == []


def test_replace_document_allows_explicit_empty_replace(monkeypatch) -> None:
    store = LangChainChromaStore.__new__(LangChainChromaStore)
    deleted: list[str] = []

    monkeypatch.setattr(store, "list_document_chunk_ids", lambda doc_id: [f"{doc_id}:0"])
    monkeypatch.setattr(store, "delete_ids", lambda ids: deleted.extend(ids) or len(ids))

    result = store.replace_document(
        doc_id="doc-1",
        ids=[],
        documents=[],
        metadatas=[],
        embeddings=[],
        allow_empty_replace=True,
    )

    assert result.upserted == 0
    assert result.deleted == 1
    assert deleted == ["doc-1:0"]
