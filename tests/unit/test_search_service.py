"""Unit tests for SearchService."""

from app.services.search_service import SearchService


class FakeEmbedder:
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3] for _ in texts]


def _fake_search_collection(
    query_embedding: list[float],
    top_k: int,
    filters: dict[str, str] | None = None,
) -> list[dict[str, object]]:
    return [
        {
            "text": "filtered result",
            "metadata": {
                "doc_id": "d1",
                "chunk_id": "c1",
                "source": "kb/allowed.md",
                "section": "Storage",
                "location": "Storage",
                "ref": "allowed > Storage",
                "title": "allowed",
                "page": "",
                "anchor": "",
            },
            "distance": 0.1,
        }
    ]


def _patch_search_service(monkeypatch) -> None:
    monkeypatch.setattr("app.services.search_service.get_embedding_backend", lambda model_name: FakeEmbedder())
    monkeypatch.setattr("app.services.search_service.search_collection", _fake_search_collection)


def test_search_service_passes_filters_to_vectorstore(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def capturing_search(
        query_embedding: list[float],
        top_k: int,
        filters: dict[str, str] | None = None,
    ) -> list[dict[str, object]]:
        captured["query_embedding"] = query_embedding
        captured["top_k"] = top_k
        captured["filters"] = filters
        return _fake_search_collection(query_embedding, top_k, filters)

    monkeypatch.setattr("app.services.search_service.get_embedding_backend", lambda model_name: FakeEmbedder())
    monkeypatch.setattr("app.services.search_service.search_collection", capturing_search)

    service = SearchService()
    result = service.search(
        query="where is data stored",
        top_k=2,
        filters={"source": "kb/allowed.md", "section": "Storage"},
    )

    assert captured["top_k"] == 2
    assert captured["filters"] == {"source": "kb/allowed.md", "section": "Storage"}
    assert result["hits"][0]["source"] == "kb/allowed.md"


def test_search_returns_citation_per_hit(monkeypatch) -> None:
    """Each hit must carry a citation with all standardized fields."""
    _patch_search_service(monkeypatch)

    service = SearchService()
    result = service.search(query="test", top_k=1)

    hit = result["hits"][0]
    assert "citation" in hit
    citation = hit["citation"]
    assert citation["doc_id"] == "d1"
    assert citation["chunk_id"] == "c1"
    assert citation["source"] == "kb/allowed.md"
    assert isinstance(citation["snippet"], str)
    assert citation["page"] is None  # empty string → None
    assert citation["anchor"] is None
    assert citation["title"] == "allowed"
    assert citation["section"] == "Storage"


def test_search_hit_still_has_text_and_distance(monkeypatch) -> None:
    """The hit itself retains text and distance alongside citation."""
    _patch_search_service(monkeypatch)

    service = SearchService()
    result = service.search(query="test", top_k=1)

    hit = result["hits"][0]
    assert hit["text"] == "filtered result"
    assert hit["distance"] == 0.1
