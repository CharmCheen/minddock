"""LLM provider contract."""

from abc import ABC, abstractmethod


EvidenceItem = dict[str, object]


class LLMProvider(ABC):
    """Port for text generation used by workflows."""

    @abstractmethod
    def name(self) -> str:
        """Return the provider identifier."""

    @abstractmethod
    def generate(self, query: str, evidence: list[EvidenceItem]) -> str:
        """Generate a grounded answer from the query and retrieved evidence."""
