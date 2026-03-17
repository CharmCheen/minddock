from app.services.search_service import SearchService


class FakeEmbedder:
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3] for _ in texts]


def test_search_service_passes_filters_to_vectorstore(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_search_collection(
        query_embedding: list[float],
        top_k: int,
        filters: dict[str, str] | None = None,
    ) -> list[dict[str, object]]:
        captured["query_embedding"] = query_embedding
        captured["top_k"] = top_k
        captured["filters"] = filters
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
                },
                "distance": 0.1,
            }
        ]

    monkeypatch.setattr("app.services.search_service.get_embedding_backend", lambda model_name: FakeEmbedder())
    monkeypatch.setattr("app.services.search_service.search_collection", fake_search_collection)

    service = SearchService()
    result = service.search(
        query="where is data stored",
        top_k=2,
        filters={"source": "kb/allowed.md", "section": "Storage"},
    )

    assert captured["top_k"] == 2
    assert captured["filters"] == {"source": "kb/allowed.md", "section": "Storage"}
    assert result["hits"][0]["source"] == "kb/allowed.md"
