"""Document parser contract."""

from abc import ABC, abstractmethod
from typing import Any, Dict


class DocumentParser(ABC):
    """Port for turning source payloads into structured text output."""

    @abstractmethod
    def name(self) -> str:
        """Return the parser identifier."""

    @abstractmethod
    def parse(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Parse raw payload into a normalized structure.

        Recommended keys in result:
        - text: str
        - sections: list (optional)
        - location_map/pages: dict/list (optional)
        - meta: dict (optional)
        """
