"""RD/RT allocation helpers for vpnv4 driver."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Dict, Tuple


@dataclass
class Allocation:
    """Represents RD/RT values assigned to a namespace."""

    rd: str
    import_rt: str
    export_rt: str

    def as_tuple(self) -> Tuple[str, str, str]:
        return self.rd, self.import_rt, self.export_rt


class DeterministicAllocator:
    """Deterministically assign RD/RT values based on namespace name.

    The allocator hashes the namespace string into a 16-bit integer space to
    avoid exposing raw sequential IDs while keeping values stable between runs.
    Collisions are resolved by linear probing which is sufficient for the small
    number of tenants we expect in the lab environment.

    Parameters
    ----------
    rd_base:
        Base ASN (``<asn>:<id>``) used to render Route Distinguishers.
    rt_base:
        Base ASN for Route Targets.  Typically the same as ``rd_base`` but we
        keep it configurable in case the FortiGate environment uses different
        policies.
    max_id:
        Upper bound (exclusive) for generated integer identifiers.
    """

    def __init__(self, rd_base: int, rt_base: int, max_id: int = 65535) -> None:
        self._rd_base = rd_base
        self._rt_base = rt_base
        self._max_id = max_id
        self._registry: Dict[str, Allocation] = {}
        self._reverse: Dict[int, str] = {}

    def _hash_namespace(self, namespace: str) -> int:
        digest = hashlib.sha256(namespace.encode("utf-8")).digest()
        return int.from_bytes(digest[:2], "big") % self._max_id

    def _format_rd(self, identifier: int) -> str:
        return f"{self._rd_base}:{identifier}"

    def _format_rt(self, identifier: int) -> str:
        return f"{self._rt_base}:{identifier}"

    def allocate(self, namespace: str) -> Allocation:
        if namespace in self._registry:
            return self._registry[namespace]

        candidate = self._hash_namespace(namespace)
        start = candidate
        while candidate in self._reverse and self._reverse[candidate] != namespace:
            candidate = (candidate + 1) % self._max_id
            if candidate == start:
                raise RuntimeError("Allocator exhausted identifier space")

        allocation = Allocation(
            rd=self._format_rd(candidate),
            import_rt=self._format_rt(candidate),
            export_rt=self._format_rt(candidate),
        )
        self._registry[namespace] = allocation
        self._reverse[candidate] = namespace
        return allocation

    def lookup(self, namespace: str) -> Allocation | None:
        return self._registry.get(namespace)

