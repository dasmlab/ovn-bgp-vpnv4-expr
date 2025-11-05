"""Minimal ovn-bgp-agent style integration helpers for the vpnv4 driver.

The real ovn-bgp-agent project provides a fairly involved driver registry and
event processing pipeline. For the purposes of this repository we implement a
lightweight subset so the vpnv4 driver can be exercised end-to-end in tests and
lab environments without depending on the full agent source tree.

This package behaves as a *namespace package* layered on top of the upstream
`ovn_bgp_agent` distribution. Any modules we don't provide locally will be
resolved from the installed project (e.g. `ovn_bgp_agent.config`,
`ovn_bgp_agent.drivers.openstack.utils`, ...).
"""

from pkgutil import extend_path

__path__ = extend_path(__path__, __name__)

from .events import NamespaceDelete, NamespaceUpsert  # noqa: F401
from .registry import DriverRegistry  # noqa: F401

__all__ = [
    "DriverRegistry",
    "NamespaceDelete",
    "NamespaceUpsert",
]


