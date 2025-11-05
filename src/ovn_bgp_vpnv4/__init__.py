"""OVN BGP Agent VPNv4 driver scaffolding.

This package hosts the experimental vpnv4 route driver that will be wired into
``ovn-bgp-agent`` once the upstream integration points are in place.  The goal
is to keep the module self-contained so we can iterate on the RD/RT allocation
logic, FRR configuration rendering and kernel plumbing without having to vendor
the entire agent codebase yet.

The driver exposed via :class:`ovn_bgp_vpnv4.driver.VPNv4RouteDriver` is a thin
orchestrator that will eventually satisfy the interface expected by the
upstream EVPN driver.  At the moment it focuses on:

* allocating deterministic Route Distinguishers / Route Targets per tenant
  namespace;
* tracking per-VRF prefix sets that must be announced via MP-BGP vpnv4;
* materialising FRR configuration snippets so the lab FRR container can pick
  them up; and
* providing a structure to plug in kernel routing table programming when we
  start exporting pod subnets.

The package is deliberately lightweight and pure-Python so unit tests can run
in CI without depending on system utilities or FRR binaries.
"""

from .driver import VPNv4RouteDriver  # noqa: F401

__all__ = ["VPNv4RouteDriver"]

