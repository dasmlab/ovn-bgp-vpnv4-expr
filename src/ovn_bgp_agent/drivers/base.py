"""Abstract interfaces for namespace-aware drivers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Sequence


class NamespaceDriver(ABC):
    """Base class for driver adapters managed by :class:`DriverRegistry`."""

    @abstractmethod
    def on_namespace_upsert(self, namespace: str, prefixes: Sequence[str]) -> None:
        """Apply ``prefixes`` as the desired state for ``namespace``."""

    @abstractmethod
    def on_namespace_delete(self, namespace: str) -> None:
        """Remove any state associated with ``namespace``."""


