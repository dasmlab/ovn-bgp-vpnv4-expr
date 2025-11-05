"""File-based namespace watcher."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from threading import Event, Thread
from typing import Dict, Iterable, Sequence

from ovn_bgp_agent import DriverRegistry
from ovn_bgp_agent.events import NamespaceDelete, NamespaceUpsert

LOG = logging.getLogger(__name__)


def _normalise(prefixes: Iterable[str]) -> Sequence[str]:
    unique = dict.fromkeys(str(p) for p in prefixes)
    return list(unique.keys())


def _extract_state(payload: dict) -> Dict[str, Sequence[str]]:
    tenants = payload.get("tenants")
    if tenants is None:
        raise ValueError("tenants file missing 'tenants' key")

    state: Dict[str, Sequence[str]] = {}
    for tenant in tenants:
        namespace = tenant.get("namespace")
        prefixes = tenant.get("prefixes", [])
        if namespace is None:
            continue
        state[str(namespace)] = _normalise(prefixes)
    return state


class FileNamespaceWatcher(Thread):
    """Poll a JSON tenants file and publish namespace events."""

    def __init__(
        self,
        registry: DriverRegistry,
        path: Path,
        interval: float,
        stop_event: Event,
    ) -> None:
        super().__init__(daemon=True)
        self._registry = registry
        self._path = Path(path)
        self._interval = interval
        self._stop_event = stop_event
        self._state: Dict[str, Sequence[str]] = {}

    def run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.poll()
            except Exception:  # pragma: no cover - logged below
                LOG.exception("file watcher encountered an error")
            self._stop_event.wait(self._interval)

    def poll(self) -> None:
        if not self._path.exists():
            LOG.debug("tenants file %s does not exist yet", self._path)
            return

        try:
            payload = json.loads(self._path.read_text())
        except json.JSONDecodeError as exc:
            LOG.warning("failed to parse tenants file %s: %s", self._path, exc)
            return

        try:
            desired = _extract_state(payload)
        except ValueError as exc:
            LOG.warning("invalid tenants file %s: %s", self._path, exc)
            return

        for namespace, prefixes in desired.items():
            if self._state.get(namespace) != prefixes:
                LOG.debug(
                    "namespace %s updated with prefixes %s", namespace, prefixes
                )
                self._registry.handle(NamespaceUpsert(namespace, prefixes))

        for namespace in set(self._state) - set(desired):
            LOG.debug("namespace %s removed", namespace)
            self._registry.handle(NamespaceDelete(namespace))

        self._state = desired


