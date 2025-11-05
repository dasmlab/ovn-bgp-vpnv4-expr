"""Event primitives consumed by the lightweight driver registry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class NamespaceUpsert:
    """Represents the desired state for a namespace/VRF.

    The controller is expected to publish a full prefix list whenever the
    namespace changes so that drivers can reconcile their configuration.
    """

    namespace: str
    prefixes: Sequence[str]


@dataclass(frozen=True)
class NamespaceDelete:
    """Signals that a namespace should be removed entirely."""

    namespace: str


