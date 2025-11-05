"""Configuration data structures for the vpnv4 driver.

These light-weight dataclasses are used by the driver and renderer modules to
describe neighbours, VRFs and global BGP settings without introducing a hard
dependency on the upstream agent configuration loader.  Once we vendor the
original project we can swap these classes with the canonical equivalents or
extend the conversion logic accordingly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Iterable, List, Optional, Sequence


class AddressFamily(Enum):
    """Supported address families for the vpnv4 driver.

    We only care about vpnv4/vpnv6 today, but keeping the enumeration flexible
    makes it easier to extend in the future or share bits with the existing
    EVPN implementation.
    """

    VPNV4 = auto()
    VPNV6 = auto()


@dataclass(frozen=True)
class Neighbor:
    """BGP neighbour description.

    Attributes
    ----------
    address:
        The neighbour IP address as a string.
    remote_asn:
        The peer Autonomous System Number.
    families:
        The address families to enable for this neighbour.  FortiGate expects
        vpnv4 (and optionally vpnv6 in the future).
    description:
        Optional human readable label that will be propagated into FRR config
        comments to aid troubleshooting.
    """

    address: str
    remote_asn: int
    families: Sequence[AddressFamily] = (AddressFamily.VPNV4,)
    description: Optional[str] = None


@dataclass(frozen=True)
class VRFDefinition:
    """Represents a logical tenant VRF exported via vpnv4."""

    name: str
    rd: str
    import_rts: Sequence[str]
    export_rts: Sequence[str]
    label: int = 0  # implicit-null placeholder by default

    def all_route_targets(self) -> List[str]:
        """Return the union of import/export RTs as a de-duplicated list."""

        # Using ``list(dict.fromkeys())`` preserves order while de-duplicating.
        return list(dict.fromkeys([*self.import_rts, *self.export_rts]).keys())


@dataclass(frozen=True)
class GlobalConfig:
    """Driver level configuration knobs."""

    local_asn: int
    router_id: str
    rd_base: int
    rt_base: int
    neighbours: Sequence[Neighbor]
    vrf_label_base: int = 0  # used when we start assigning non-zero labels
    export_ipv6: bool = False

    def neighbour_for(self, address: str) -> Optional[Neighbor]:
        """Return the neighbour matching ``address`` if present."""

        return next((n for n in self.neighbours if n.address == address), None)


@dataclass
class TenantContext:
    """Runtime data for a tenant/namespace."""

    namespace: str
    vrf: VRFDefinition
    advertised_prefixes: List[str] = field(default_factory=list)

    def add_prefixes(self, prefixes: Iterable[str]) -> None:
        missing = [p for p in prefixes if p not in self.advertised_prefixes]
        self.advertised_prefixes.extend(missing)

    def withdraw_prefixes(self, prefixes: Iterable[str]) -> None:
        for prefix in prefixes:
            if prefix in self.advertised_prefixes:
                self.advertised_prefixes.remove(prefix)

