"""Tool plugin contracts based on OpenAPI metadata."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List


class ToolPlugin(ABC):
    """Port for plugin metadata and tool discovery."""

    @abstractmethod
    def name(self) -> str:
        """Return plugin name."""

    @abstractmethod
    def openapi_spec(self) -> Dict[str, Any]:
        """Return OpenAPI specification payload."""

    @abstractmethod
    def list_operations(self) -> List[str]:
        """Return callable operation identifiers."""


class ToolRunner(ABC):
    """Port for executing discovered tool operations."""

    @abstractmethod
    def run(self, operation_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute an operation and return normalized JSON result."""
