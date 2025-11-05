"""Tiny driver registry used for the vpnv4 integration tests."""

from __future__ import annotations

from typing import Dict

from .drivers import NamespaceDriver
from .events import NamespaceDelete, NamespaceUpsert


class DriverRegistry:
    """Dispatch namespace events to registered driver adapters."""

    def __init__(self) -> None:
        self._drivers: Dict[str, NamespaceDriver] = {}

    def register(self, name: str, driver: NamespaceDriver) -> None:
        if name in self._drivers:
            raise ValueError(f"driver '{name}' already registered")
        self._drivers[name] = driver

    def unregister(self, name: str) -> None:
        self._drivers.pop(name, None)

    def handle(self, event: NamespaceUpsert | NamespaceDelete) -> None:
        if isinstance(event, NamespaceUpsert):
            self._on_namespace_upsert(event)
        elif isinstance(event, NamespaceDelete):
            self._on_namespace_delete(event)
        else:
            raise TypeError(f"Unsupported event type: {type(event)!r}")

    def _on_namespace_upsert(self, event: NamespaceUpsert) -> None:
        for driver in self._drivers.values():
            driver.on_namespace_upsert(event.namespace, event.prefixes)

    def _on_namespace_delete(self, event: NamespaceDelete) -> None:
        for driver in self._drivers.values():
            driver.on_namespace_delete(event.namespace)


