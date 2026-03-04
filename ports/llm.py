"""LLM provider contract."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List


class LLMProvider(ABC):
    """Port for text generation used by workflows."""

    @abstractmethod
    def name(self) -> str:
        """Return the provider identifier."""

    @abstractmethod
    def generate(self, messages: List[Dict[str, Any]], **kwargs: Any) -> str:
        """Generate text output from message history."""
