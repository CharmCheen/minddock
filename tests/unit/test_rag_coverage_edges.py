from __future__ import annotations

from app.rag.ingest import _build_chunk_documents
from app.rag.retrieval_models import RetrievalFilters, RetrievedChunk
from app.rag.source_models import SourceDescriptor, SourceLoadResult
from app.rag.splitter import split_text
from app.rag.vectorstore import LangChainChromaStore


def test_split_text_returns_no_chunks_for_blank_input(monkeypatch) -> None:
    monkeypatch.setattr("app.rag.splitter.token_count", lambda text: len(text))

    assert split_text(" \n\n\t ") == []


def test_split_text_preserves_detected_section_titles(monkeypatch) -> None:
    monkeypatch.setattr("app.rag.splitter.token_count", lambda text: len(text))
    text = """
# Intro
Alpha sentence.

1 | METHODS
Beta sentence.

2 Results
Gamma sentence.
"""

    chunks = split_text(text, chunk_size=100, overlap=10)

    assert [(chunk["section"], chunk["text"]) for chunk in chunks] == [
        ("Intro", "Alpha sentence."),
        ("1 | METHODS", "Beta sentence."),
        ("2 Results", "Gamma sentence."),
    ]


def test_split_text_uses_sentence_windows_for_long_paragraph(monkeypatch) -> None:
    monkeypatch.setattr("app.rag.splitter.token_count", lambda text: len(text))

    chunks = split_text(
        "Alpha beta. Gamma delta. Epsilon zeta. Eta theta.",
        chunk_size=24,
        overlap=12,
    )

    texts = [chunk["text"] for chunk in chunks]
    assert len(texts) > 1
    assert texts[0] == "Alpha beta. Gamma delta."
    assert texts[1].startswith("Gamma delta.")


def test_split_text_splits_single_long_sentence_at_character_boundaries(monkeypatch) -> None:
    monkeypatch.setattr("app.rag.splitter.token_count", lambda text: len(text))

    chunks = split_text("a" * 42, chunk_size=10, overlap=3)

    texts = [chunk["text"] for chunk in chunks]
    assert len(texts) > 1
    assert all(1 <= len(text) <= 10 for text in texts)


def test_page_mode_falls_back_when_structured_chunks_are_empty(monkeypatch) -> None:
    descriptor = SourceDescriptor(source="report.pdf", source_type="file")
    load_result = SourceLoadResult(
        descriptor=descriptor,
        text="[page 1]\nAlpha page text.\n\n[page 2]\nBeta page text.",
        title="Report",
        metadata={
            "_page_blocks": [{"page": 1, "blocks": []}, {"page": 2, "blocks": []}],
            "loader_name": "file.pdf",
        },
    )
    monkeypatch.setattr("app.rag.ingest.structured_pdf_chunks", lambda *args, **kwargs: [])
    monkeypatch.setattr("app.rag.ingest._chunk_by_tokens", lambda text, chunk_size, overlap: [text])

    documents = _build_chunk_documents(load_result=load_result, page_mode=True)

    assert [doc.page_content for doc in documents] == ["Alpha page text.", "Beta page text."]
    assert [doc.metadata["chunk_id"] for doc in documents] == [
        f"{descriptor.doc_id}:0",
        f"{descriptor.doc_id}:1",
    ]
    assert [doc.metadata["page"] for doc in documents] == ["1", "2"]
    assert all("_page_blocks" not in doc.metadata for doc in documents)
    assert all(doc.metadata["source_version"] == doc.metadata["content_hash"] for doc in documents)


def test_chunk_document_builder_ignores_empty_page_mode_text() -> None:
    descriptor = SourceDescriptor(source="empty.pdf", source_type="file")
    load_result = SourceLoadResult(descriptor=descriptor, text=" \n\n ", title="Empty")

    assert _build_chunk_documents(load_result=load_result, page_mode=True) == []


class _FakeCollection:
    def __init__(self, *, count_value: int = 0, get_result: dict | None = None, query_result: dict | None = None) -> None:
        self.count_value = count_value
        self.get_result = get_result or {}
        self.query_result = query_result or {}
        self.get_calls: list[dict] = []
        self.query_calls: list[dict] = []

    def count(self) -> int:
        return self.count_value

    def get(self, **kwargs):
        self.get_calls.append(kwargs)
        return self.get_result

    def query(self, **kwargs):
        self.query_calls.append(kwargs)
        return self.query_result


class _FakeStore:
    def __init__(self, collection: _FakeCollection) -> None:
        self._collection = collection
        self.get_calls: list[dict] = []

    def get(self, **kwargs):
        self.get_calls.append(kwargs)
        return self._collection.get_result


def _store_with(collection: _FakeCollection) -> LangChainChromaStore:
    store = LangChainChromaStore.__new__(LangChainChromaStore)
    store._store = _FakeStore(collection)
    return store


def test_vectorstore_get_chunks_by_ids_deduplicates_and_applies_filters() -> None:
    collection = _FakeCollection(
        get_result={
            "ids": ["b", "a"],
            "documents": ["Blocked", "Allowed"],
            "metadatas": [
                {"doc_id": "doc", "chunk_id": "b", "source": "blocked.md", "source_type": "file"},
                {"doc_id": "doc", "chunk_id": "a", "source": "allowed.md", "source_type": "file"},
            ],
        }
    )
    store = _store_with(collection)

    hits = store.get_chunks_by_ids(["a", "b", "a", ""], filters=RetrievalFilters(sources=("allowed.md",)))

    assert [call["ids"] for call in collection.get_calls] == [["a", "b"]]
    assert [hit.chunk_id for hit in hits] == ["a"]
    assert hits[0].text == "Allowed"


def test_vectorstore_search_by_vector_handles_empty_and_filtered_results() -> None:
    empty_store = _store_with(_FakeCollection(count_value=0))
    assert empty_store.search_by_vector([0.1], top_k=3) == []

    collection = _FakeCollection(
        count_value=3,
        query_result={
            "documents": [["Alpha", "Beta"]],
            "metadatas": [[
                {"doc_id": "doc", "chunk_id": "doc:1", "source": "a.md", "source_type": "file", "page": "2"},
                {"doc_id": "doc", "chunk_id": "doc:2", "source": "b.md", "source_type": "file", "page": "9"},
            ]],
            "distances": [[0.1, 0.2]],
        },
    )
    store = _store_with(collection)

    hits = store.search_by_vector([0.1], top_k=2, filters=RetrievalFilters(page_from=2, page_to=2))

    assert [hit.chunk_id for hit in hits] == ["doc:1"]
    assert collection.query_calls[0]["n_results"] == 3


def test_vectorstore_get_document_chunks_tolerates_sparse_metadata() -> None:
    collection = _FakeCollection(
        get_result={
            "ids": ["doc:0", "doc:1"],
            "documents": ["First chunk"],
            "metadatas": [{"source": "source.md", "section": "Intro"}],
        }
    )
    store = _store_with(collection)

    rows = store.get_document_chunks("doc", include_text=True)

    assert rows[0]["chunk_id"] == "doc:0"
    assert rows[0]["source"] == "source.md"
    assert rows[0]["text"] == "First chunk"
    assert rows[1]["chunk_id"] == "doc:1"
    assert rows[1]["text"] == ""


def test_vectorstore_neighbor_chunks_use_order_metadata_and_keep_hit_fallback() -> None:
    hit_without_doc = RetrievedChunk.from_raw("Loose", {"chunk_id": "loose", "source": "s"}, None)
    store_without_doc = _store_with(_FakeCollection())
    assert store_without_doc.get_neighbor_chunks(hit_without_doc, before=1, after=1) == [hit_without_doc]

    collection = _FakeCollection(
        get_result={
            "documents": ["First", "Second", "Third"],
            "metadatas": [
                {"doc_id": "doc", "chunk_id": "doc:1", "source": "s", "order_in_doc": "1"},
                {"doc_id": "doc", "chunk_id": "doc:2", "source": "s", "order_in_doc": "2"},
                {"doc_id": "doc", "chunk_id": "doc:3", "source": "s", "order_in_doc": "3"},
            ],
        }
    )
    store = _store_with(collection)
    hit = RetrievedChunk.from_raw("Second", {"doc_id": "doc", "chunk_id": "doc:2", "source": "s", "order_in_doc": "2"}, None)

    neighbors = store.get_neighbor_chunks(hit, before=1, after=0)

    assert [chunk.chunk_id for chunk in neighbors] == ["doc:1", "doc:2"]


def test_vectorstore_inspect_source_builds_admin_metadata_and_sorted_previews() -> None:
    collection = _FakeCollection(
        get_result={
            "documents": ["Summary text", "Main text"],
            "metadatas": [
                {
                    "doc_id": "doc",
                    "chunk_id": "doc:1",
                    "source": "source.md",
                    "source_type": "file",
                    "title": "Source",
                    "section": "Summary",
                    "page": "2",
                    "order_in_doc": "2",
                    "is_derived": "true",
                    "derived_kind": "media_summary",
                    "derived_from": "doc:0",
                    "derived_basis": "transcript",
                    "content_hash": "hash-1",
                    "last_ingested_at": "2026-05-13T00:00:00Z",
                },
                {
                    "doc_id": "doc",
                    "chunk_id": "doc:0",
                    "source": "source.md",
                    "source_type": "file",
                    "title": "Source",
                    "section": "Intro",
                    "page": "1",
                    "order_in_doc": "1",
                    "requested_url": "https://example.test/source",
                    "final_url": "https://example.test/final",
                    "domain": "example.test",
                    "content_hash": "hash-1",
                },
            ],
        }
    )
    store = _store_with(collection)

    result = store.inspect_source("doc", limit=2, offset=0, include_admin_metadata=True)

    assert result is not None
    assert result.detail.entry.chunk_count == 2
    assert result.detail.entry.pages == (1, 2)
    assert result.detail.entry.sections == ("Intro", "Summary")
    assert result.detail.entry.state is not None
    assert result.detail.entry.state.content_hash == "hash-1"
    assert result.admin_metadata["requested_url"] == "https://example.test/source"
    assert result.chunk_page.chunks[0].chunk_id == "doc:0"
    assert result.chunk_page.chunks[1].admin_metadata["is_derived"] == "true"
