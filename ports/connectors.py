"""Data source connector contract."""

from abc import ABC, abstractmethod
from typing import Iterable

from domain.models import RawDoc


class DataConnector(ABC):
    """Port for reading source data and emitting RawDoc objects."""

    @abstractmethod
    def name(self) -> str:
        """Return the connector identifier."""

    @abstractmethod
    def fetch(self) -> Iterable[RawDoc]:
        """Yield normalized raw documents.

        Contract:
        - Should be idempotent or explicitly incremental.
        - Must not write directly to vector storage.
        """
