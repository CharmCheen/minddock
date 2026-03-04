"""Vector store contract."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List


class VectorStore(ABC):
    """Port for vector upsert and retrieval."""

    @abstractmethod
    def name(self) -> str:
        """Return the vector store identifier."""

    @abstractmethod
    def upsert(self, items: List[Dict[str, Any]]) -> None:
        """Insert or update vector items.

        Expected item fields:
        - doc_id, chunk_id, text, embedding
        - meta, location, section_path
        """

    @abstractmethod
    def search(self, query: str, top_k: int, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Return ranked hits.

        Expected hit fields:
        - doc_id, chunk_id, text, score, location, meta
        """
