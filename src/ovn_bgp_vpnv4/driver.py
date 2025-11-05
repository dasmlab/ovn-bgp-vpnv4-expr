"""vpnv4 route driver skeleton.

This module provides a high-level orchestrator that mirrors the structure of
the existing EVPN driver in ``ovn-bgp-agent``.  It currently tracks namespace
VRFs, applies deterministic RD/RT allocations and renders FRR configuration
snippets that can be consumed by the lab FRR container.  Direct integration
with the upstream agent will hook these operations into the agent's event loop
and netlink interactions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

from .allocator import DeterministicAllocator
from .config import GlobalConfig, TenantContext, VRFDefinition
from .frr import FRRConfigRenderer, RenderResult

LOG = logging.getLogger(__name__)


@dataclass
class DriverState:
    """Mutable runtime state tracked by the driver."""

    tenants: Dict[str, TenantContext]
    last_render: Optional[RenderResult] = None


class VPNv4RouteDriver:
    """Experimental driver that advertises namespaces via MP-BGP vpnv4."""

    def __init__(
        self,
        config: GlobalConfig,
        output_dir: Path,
        allocator: Optional[DeterministicAllocator] = None,
        include_globals: bool = False,
    ) -> None:
        self._config = config
        self._allocator = allocator or DeterministicAllocator(
            rd_base=config.rd_base, rt_base=config.rt_base
        )
        self._state = DriverState(tenants={})
        self._renderer = FRRConfigRenderer(
            config,
            output_dir,
            include_globals=include_globals,
        )

    # ------------------------------------------------------------------
    # VRF lifecycle helpers
    # ------------------------------------------------------------------
    def ensure_namespace(self, namespace: str) -> TenantContext:
        """Ensure ``namespace`` has a VRF allocation and return its context."""

        if namespace in self._state.tenants:
            return self._state.tenants[namespace]

        allocation = self._allocator.allocate(namespace)
        vrf = VRFDefinition(
            name=namespace,
            rd=allocation.rd,
            import_rts=[allocation.import_rt],
            export_rts=[allocation.export_rt],
        )

        tenant = TenantContext(namespace=namespace, vrf=vrf)
        self._state.tenants[namespace] = tenant
        LOG.info(
            "Allocated vpnv4 VRF for namespace '%s': rd=%s rt=%s",
            namespace,
            allocation.rd,
            allocation.import_rt,
        )
        return tenant

    def withdraw_namespace(self, namespace: str) -> Optional[TenantContext]:
        """Drop tracking for ``namespace`` and trigger FRR re-render."""

        tenant = self._state.tenants.pop(namespace, None)
        if tenant:
            LOG.info("Removed vpnv4 tenant '%s'", namespace)
            self.render()
        return tenant

    # ------------------------------------------------------------------
    # Prefix handling
    # ------------------------------------------------------------------
    def advertise_prefixes(self, namespace: str, prefixes: Iterable[str]) -> TenantContext:
        tenant = self.ensure_namespace(namespace)
        tenant.add_prefixes(prefixes)
        LOG.debug("Namespace %s advertising prefixes: %s", namespace, prefixes)
        self.render()
        return tenant

    def withdraw_prefixes(self, namespace: str, prefixes: Iterable[str]) -> Optional[TenantContext]:
        tenant = self._state.tenants.get(namespace)
        if not tenant:
            LOG.debug("withdraw_prefixes called for unknown namespace '%s'", namespace)
            return None

        tenant.withdraw_prefixes(prefixes)
        LOG.debug("Namespace %s withdrew prefixes: %s", namespace, prefixes)
        self.render()
        return tenant

    def synchronize_prefixes(
        self, namespace: str, prefixes: Iterable[str]
    ) -> TenantContext:
        """Apply ``prefixes`` as the desired state for ``namespace``.

        This helper is designed for higher-level controllers (e.g. the
        upstream ovn-bgp-agent watcher) which reconcile the full list of
        prefixes each time they observe a change.  It avoids redundant render
        cycles when the computed prefix set does not change.
        """

        tenant = self.ensure_namespace(namespace)
        desired = list(dict.fromkeys(prefixes))
        if tenant.advertised_prefixes == desired:
            LOG.debug("Namespace %s already advertising desired prefixes", namespace)
            return tenant

        tenant.set_prefixes(desired)
        LOG.debug("Namespace %s synchronized prefixes: %s", namespace, desired)
        self.render()
        return tenant

    # ------------------------------------------------------------------
    # Rendering / orchestration
    # ------------------------------------------------------------------
    def render(self) -> RenderResult:
        tenants = list(self._state.tenants.values())
        result = self._renderer.render(tenants)
        self._state.last_render = result
        LOG.info("Rendered FRR vpnv4 config to %s", result.output_path)
        return result

    def sync(self) -> RenderResult:
        """Force re-render regardless of state changes."""

        return self.render()

    # ------------------------------------------------------------------
    # Introspection helpers (useful for tests / CLI)
    # ------------------------------------------------------------------
    def list_tenants(self) -> Sequence[TenantContext]:
        return list(self._state.tenants.values())

    def get_rendered_config(self) -> Optional[str]:
        if self._state.last_render:
            return self._state.last_render.config_text
        return None

