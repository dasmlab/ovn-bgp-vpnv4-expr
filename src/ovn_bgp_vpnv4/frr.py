"""FRR configuration helpers for vpnv4 export."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from .config import AddressFamily, GlobalConfig, Neighbor, TenantContext, VRFDefinition


FRR_HEADER = """!
frr version 9.x
frr defaults traditional
service integrated-vtysh-config
!
"""


@dataclass
class RenderResult:
    """Result of an FRR rendering operation."""

    config_text: str
    output_path: Path


class FRRConfigRenderer:
    """Render FRR configuration snippets for the vpnv4 driver."""

    def __init__(
        self,
        config: GlobalConfig,
        output_dir: Path,
        *,
        include_globals: bool = False,
    ) -> None:
        self._config = config
        self._output_dir = output_dir
        self._include_globals = include_globals

    def render(self, tenants: Sequence[TenantContext]) -> RenderResult:
        sections: list[str] = []
        neighbor_addresses = [n.address for n in self._config.neighbours]
        if self._include_globals:
            sections.append(FRR_HEADER)
            sections.append(self._render_neighbors(self._config.neighbours))

        vrfs = self._render_vrfs(tenants)
        if vrfs:
            sections.append(vrfs)

        if self._include_globals:
            if neighbor_addresses:
                sections.append(self._render_route_maps())
            sections.extend(["line vty", "!"])
        elif neighbor_addresses:
            sections.append(self._render_route_maps())

        body = "\n".join([s for s in sections if s])

        self._output_dir.mkdir(parents=True, exist_ok=True)
        output_path = self._output_dir / "vpnv4.conf"
        output_path.write_text(body)

        return RenderResult(config_text=body, output_path=output_path)

    def _render_neighbors(self, neighbours: Sequence[Neighbor]) -> str:
        lines = [
            f"router bgp {self._config.local_asn}",
            f" bgp router-id {self._config.router_id}",
            " no bgp default ipv4-unicast",
        ]

        for neighbour in neighbours:
            lines.extend(self._render_neighbor_block(neighbour))

        return "\n".join(lines)

    def _render_neighbor_block(self, neighbour: Neighbor) -> Iterable[str]:
        lines = [f" neighbor {neighbour.address} remote-as {neighbour.remote_asn}"]
        if neighbour.description:
            lines.append(
                f" neighbor {neighbour.address} description {neighbour.description}"
            )
        if AddressFamily.VPNV4 in neighbour.families:
            lines.append("!")
            lines.append(" address-family ipv4 vpn")
            lines.append(f"  neighbor {neighbour.address} activate")
            lines.append(f"  neighbor {neighbour.address} send-community extended")
            lines.append(" exit-address-family")
        if AddressFamily.VPNV6 in neighbour.families and self._config.export_ipv6:
            lines.append("!")
            lines.append(" address-family ipv6 vpn")
            lines.append(f"  neighbor {neighbour.address} activate")
            lines.append(f"  neighbor {neighbour.address} send-community extended")
            lines.append(" exit-address-family")
        return lines

    def _render_vrfs(
        self,
        tenants: Sequence[TenantContext],
    ) -> str:
        return "\n".join(
            self._render_bgp_vrf_block(tenant.vrf, tenant.advertised_prefixes)
            for tenant in tenants
        )

    def _render_vrf_definition(self, vrf: VRFDefinition) -> str:
        return "\n".join([f"vrf {vrf.name}", " exit-vrf", "!"])

    def _render_bgp_vrf_block(
        self,
        vrf: VRFDefinition,
        prefixes: Sequence[str],
    ) -> str:
        lines = [f"router bgp {self._config.local_asn} vrf {vrf.name}"]
        lines.append(" no bgp network import-check")
        lines.append(" !")
        lines.append(" address-family ipv4 unicast")
        lines.append("  export vpn")
        lines.append("  import vpn")
        lines.append("  redistribute static")
        lines.append(f"  rd vpn export {vrf.rd}")
        for rt in vrf.import_rts:
            lines.append(f"  route-target vpn import {rt}")
        for rt in vrf.export_rts:
            lines.append(f"  route-target vpn export {rt}")
        if prefixes:
            for prefix in prefixes:
                lines.append(f"  network {prefix}")
        else:
            lines.append("  ! no prefixes advertised yet")
        lines.append(" exit-address-family")
        lines.append("!")
        return "\n".join(lines)

    def _render_route_maps(self) -> str:
        return "\n".join(
            [
                "route-map vpnv4-import permit 10",
                " !",
                "route-map vpnv4-export permit 10",
                " !",
            ]
        )

