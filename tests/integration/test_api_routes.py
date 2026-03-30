"""Integration tests for API routes using FastAPI TestClient."""

from fastapi.testclient import TestClient

from app.llm.mock import MockLLM
from app.main import app
from app.services.chat_service import ChatService
from app.services.summarize_service import SummarizeService


def test_root_and_health_endpoints() -> None:
    client = TestClient(app)

    root_response = client.get("/")
    health_response = client.get("/health")

    assert root_response.status_code == 200
    assert health_response.status_code == 200
    assert root_response.json()["service"] == "MindDock"
    assert health_response.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def test_search_endpoint_with_stubbed_service(monkeypatch) -> None:
    from app.api import routes

    client = TestClient(app)

    def fake_search(query: str, top_k: int, filters: dict[str, str] | None = None) -> dict[str, object]:
        return {
            "query": query,
            "top_k": top_k,
            "hits": [
                {
                    "text": "stubbed hit",
                    "doc_id": "d1",
                    "chunk_id": "c1",
                    "source": "kb/doc.md",
                    "distance": 0.1,
                    "citation": {
                        "doc_id": "d1",
                        "chunk_id": "c1",
                        "source": "kb/doc.md",
                        "snippet": "stubbed hit",
                        "page": None,
                        "anchor": None,
                        "title": None,
                        "section": None,
                        "location": None,
                        "ref": "kb/doc.md",
                    },
                }
            ],
        }

    monkeypatch.setattr(routes.search_service, "search", fake_search)

    response = client.post("/search", json={"query": "test query", "top_k": 1})

    assert response.status_code == 200
    body = response.json()
    assert body["query"] == "test query"
    assert body["hits"][0]["chunk_id"] == "c1"
    assert body["hits"][0]["citation"]["snippet"] == "stubbed hit"
    assert body["hits"][0]["citation"]["page"] is None


def test_search_endpoint_forwards_filters(monkeypatch) -> None:
    from app.api import routes

    client = TestClient(app)
    captured: dict[str, object] = {}

    def fake_search(query: str, top_k: int, filters: dict[str, str] | None = None) -> dict[str, object]:
        captured["filters"] = filters
        return {
            "query": query,
            "top_k": top_k,
            "hits": [],
        }

    monkeypatch.setattr(routes.search_service, "search", fake_search)

    response = client.post(
        "/search",
        json={
            "query": "test query",
            "top_k": 1,
            "filters": {"source": "kb/doc.md", "section": "Storage"},
        },
    )

    assert response.status_code == 200
    assert captured["filters"] == {"source": "kb/doc.md", "section": "Storage"}


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

def test_chat_endpoint_with_stubbed_service(monkeypatch) -> None:
    from app.api import routes

    client = TestClient(app)

    def fake_chat(query: str, top_k: int, filters: dict[str, str] | None = None) -> dict[str, object]:
        return {
            "answer": "stubbed answer",
            "citations": [
                {
                    "doc_id": "d1",
                    "chunk_id": "c1",
                    "source": "kb/doc.md",
                    "snippet": "stubbed snippet",
                    "page": None,
                    "anchor": None,
                    "title": "doc",
                    "section": "Storage",
                    "location": "Storage",
                    "ref": "doc > Storage",
                }
            ],
            "retrieved_count": 1,
        }

    monkeypatch.setattr(routes.chat_service, "chat", fake_chat)

    response = client.post("/chat", json={"query": "test query", "top_k": 1})

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "stubbed answer"
    assert body["retrieved_count"] == 1
    assert body["citations"][0]["section"] == "Storage"
    assert body["citations"][0]["page"] is None


def test_chat_endpoint_without_api_key_uses_mock_llm_and_filters(monkeypatch) -> None:
    from app.api import routes

    client = TestClient(app)

    class FakeSearchService:
        def retrieve(self, query: str, top_k: int, filters: dict[str, str] | None = None) -> list[dict[str, object]]:
            assert filters == {"source": "kb/doc.md", "section": "Storage"}
            return [
                {
                    "text": "MindDock stores chunks in local Chroma.",
                    "doc_id": "d1",
                    "chunk_id": "c1",
                    "source": "kb/doc.md",
                    "title": "doc",
                    "section": "Storage",
                    "location": "Storage",
                    "ref": "doc > Storage",
                    "page": None,
                    "anchor": None,
                    "distance": 0.1,
                }
            ]

    class PassthroughReranker:
        def rerank(self, query: str, hits: list[dict[str, object]]) -> list[dict[str, object]]:
            return hits

    class PassthroughCompressor:
        def compress(self, query: str, hits: list[dict[str, object]]) -> list[dict[str, object]]:
            return hits

    monkeypatch.setattr(
        routes,
        "chat_service",
        ChatService(
            search_service=FakeSearchService(),
            reranker=PassthroughReranker(),
            compressor=PassthroughCompressor(),
            llm=MockLLM(),
        ),
    )

    response = client.post(
        "/chat",
        json={
            "query": "data location",
            "top_k": 1,
            "filters": {"source": "kb/doc.md", "section": "Storage"},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert "data location" in body["answer"]
    assert "local Chroma" in body["answer"]
    assert body["retrieved_count"] == 1
    assert body["citations"][0]["chunk_id"] == "c1"
    assert body["citations"][0]["section"] == "Storage"
    assert body["citations"][0]["page"] is None


# ---------------------------------------------------------------------------
# Summarize
# ---------------------------------------------------------------------------

def test_summarize_endpoint_without_api_key_returns_summary(monkeypatch) -> None:
    from app.api import routes

    client = TestClient(app)

    class FakeSearchService:
        def retrieve(self, query: str, top_k: int, filters: dict[str, str] | None = None) -> list[dict[str, object]]:
            assert filters == {"source": "kb/doc.md", "section": "Storage"}
            return [
                {
                    "text": "MindDock stores chunks and metadata in local Chroma.",
                    "doc_id": "d1",
                    "chunk_id": "c1",
                    "source": "kb/doc.md",
                    "title": "doc",
                    "section": "Storage",
                    "location": "Storage",
                    "ref": "doc > Storage",
                    "page": None,
                    "anchor": None,
                    "distance": 0.1,
                }
            ]

    class PassthroughReranker:
        def rerank(self, query: str, hits: list[dict[str, object]]) -> list[dict[str, object]]:
            return hits

    class PassthroughCompressor:
        def compress(self, query: str, hits: list[dict[str, object]]) -> list[dict[str, object]]:
            return hits

    monkeypatch.setattr(
        routes,
        "summarize_service",
        SummarizeService(
            search_service=FakeSearchService(),
            reranker=PassthroughReranker(),
            compressor=PassthroughCompressor(),
            llm=MockLLM(),
        ),
    )

    response = client.post(
        "/summarize",
        json={
            "topic": "storage design",
            "top_k": 1,
            "filters": {"source": "kb/doc.md", "section": "Storage"},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert "storage design" in body["summary"]
    assert body["retrieved_count"] == 1
    assert body["citations"][0]["ref"] == "doc > Storage"


def test_summarize_endpoint_returns_insufficient_evidence_when_empty(monkeypatch) -> None:
    from app.api import routes

    client = TestClient(app)

    class EmptySearchService:
        def retrieve(self, query: str, top_k: int, filters: dict[str, str] | None = None) -> list[dict[str, object]]:
            return []

    class PassthroughReranker:
        def rerank(self, query: str, hits: list[dict[str, object]]) -> list[dict[str, object]]:
            return hits

    class PassthroughCompressor:
        def compress(self, query: str, hits: list[dict[str, object]]) -> list[dict[str, object]]:
            return hits

    monkeypatch.setattr(
        routes,
        "summarize_service",
        SummarizeService(
            search_service=EmptySearchService(),
            reranker=PassthroughReranker(),
            compressor=PassthroughCompressor(),
            llm=MockLLM(),
        ),
    )

    response = client.post("/summarize", json={"query": "storage design", "top_k": 1})

    assert response.status_code == 200
    body = response.json()
    assert body["summary"] == "证据不足，无法给出可靠结论。"
    assert body["citations"] == []
    assert body["retrieved_count"] == 0


# ---------------------------------------------------------------------------
# Ingest
# ---------------------------------------------------------------------------

def test_ingest_endpoint_with_stubbed_service(monkeypatch) -> None:
    from app.api import routes

    client = TestClient(app)

    def fake_ingest(rebuild: bool = False) -> dict[str, int]:
        return {"documents": 4, "chunks": 20}

    monkeypatch.setattr(routes.ingest_service, "ingest", fake_ingest)

    response = client.post("/ingest", json={"rebuild": False})

    assert response.status_code == 200
    body = response.json()
    assert body["documents"] == 4
    assert body["chunks"] == 20


def test_ingest_endpoint_rebuild_flag(monkeypatch) -> None:
    from app.api import routes

    client = TestClient(app)
    captured: dict[str, object] = {}

    def fake_ingest(rebuild: bool = False) -> dict[str, int]:
        captured["rebuild"] = rebuild
        return {"documents": 0, "chunks": 0}

    monkeypatch.setattr(routes.ingest_service, "ingest", fake_ingest)

    response = client.post("/ingest", json={"rebuild": True})

    assert response.status_code == 200
    assert captured["rebuild"] is True


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------

def test_search_empty_query_returns_422() -> None:
    client = TestClient(app)
    response = client.post("/search", json={"query": "   "})
    assert response.status_code == 422
