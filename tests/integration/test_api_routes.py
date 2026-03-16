from fastapi.testclient import TestClient

from app.main import app


def test_root_and_health_endpoints() -> None:
    client = TestClient(app)

    root_response = client.get("/")
    health_response = client.get("/health")

    assert root_response.status_code == 200
    assert health_response.status_code == 200
    assert root_response.json()["service"] == "MindDock"
    assert health_response.json()["status"] == "ok"


def test_search_endpoint_with_stubbed_service(monkeypatch) -> None:
    from app.api import routes

    client = TestClient(app)

    def fake_search(query: str, top_k: int) -> dict[str, object]:
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
                }
            ],
        }

    monkeypatch.setattr(routes.search_service, "search", fake_search)

    response = client.post("/search", json={"query": "test query", "top_k": 1})

    assert response.status_code == 200
    body = response.json()
    assert body["query"] == "test query"
    assert body["hits"][0]["chunk_id"] == "c1"


def test_chat_endpoint_with_stubbed_service(monkeypatch) -> None:
    from app.api import routes

    client = TestClient(app)

    def fake_chat(query: str, top_k: int) -> dict[str, object]:
        return {
            "answer": "stubbed answer",
            "citations": [
                {
                    "doc_id": "d1",
                    "chunk_id": "c1",
                    "source": "kb/doc.md",
                    "snippet": "stubbed snippet",
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
