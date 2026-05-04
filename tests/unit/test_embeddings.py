from app.rag import embeddings
from app.rag.embeddings import DummyEmbedding, get_embedding_backend


def test_qwen_dummy_fallback_preserves_expected_vector_size(monkeypatch) -> None:
    def fail_sentence_transformer(*args, **kwargs):
        raise OSError("model unavailable")

    monkeypatch.setattr(embeddings, "SentenceTransformerEmbedding", fail_sentence_transformer)

    get_embedding_backend.cache_clear()
    backend = get_embedding_backend("Qwen/Qwen3-Embedding-0.6B")
    get_embedding_backend.cache_clear()

    assert isinstance(backend, DummyEmbedding)
    assert backend.vector_size == 1024


def test_unknown_dummy_fallback_uses_default_vector_size(monkeypatch) -> None:
    def fail_sentence_transformer(*args, **kwargs):
        raise OSError("model unavailable")

    monkeypatch.setattr(embeddings, "SentenceTransformerEmbedding", fail_sentence_transformer)

    get_embedding_backend.cache_clear()
    backend = get_embedding_backend("sentence-transformers/all-MiniLM-L6-v2")
    get_embedding_backend.cache_clear()

    assert isinstance(backend, DummyEmbedding)
    assert backend.vector_size == embeddings.DEFAULT_VECTOR_SIZE
