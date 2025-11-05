"""Adapter between the vpnv4 route driver and the registry contract."""

from __future__ import annotations

from typing import Sequence

from ovn_bgp_vpnv4.driver import VPNv4RouteDriver

from .base import NamespaceDriver


class VPNv4DriverAdapter(NamespaceDriver):
    """Wrap :class:`~ovn_bgp_vpnv4.driver.VPNv4RouteDriver` for registry use."""

    def __init__(
        self,
        driver: VPNv4RouteDriver,
        *,
        maintain_empty_vrf: bool = True,
    ) -> None:
        self._driver = driver
        self._maintain_empty_vrf = maintain_empty_vrf

    @property
    def driver(self) -> VPNv4RouteDriver:
        return self._driver

    def on_namespace_upsert(self, namespace: str, prefixes: Sequence[str]) -> None:
        if prefixes or self._maintain_empty_vrf:
            self._driver.synchronize_prefixes(namespace, prefixes)
        else:
            # No prefixes requested and we are allowed to drop the VRF entirely.
            self._driver.withdraw_namespace(namespace)

    def on_namespace_delete(self, namespace: str) -> None:
        self._driver.withdraw_namespace(namespace)


def build_vpnv4_adapter(
    driver: VPNv4RouteDriver,
    *,
    maintain_empty_vrf: bool = True,
) -> VPNv4DriverAdapter:
    """Helper mirroring the builder pattern used by the upstream agent."""

    return VPNv4DriverAdapter(driver, maintain_empty_vrf=maintain_empty_vrf)


