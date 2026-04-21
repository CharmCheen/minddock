"""RAG package with lazy exports to avoid eager optional dependency imports."""

__all__ = ["get_embedding_backend", "get_vectorstore", "split_text"]


def get_embedding_backend():
    from .embeddings import get_embedding_backend as _get_embedding_backend

    return _get_embedding_backend()


def split_text(*args, **kwargs):
    from .splitter import split_text as _split_text

    return _split_text(*args, **kwargs)


def get_vectorstore():
    from .vectorstore import get_vectorstore as _get_vectorstore

    return _get_vectorstore()
