"""Driver adapters exposed to the minimal registry."""

from .base import NamespaceDriver  # noqa: F401
from .vpnv4_adapter import VPNv4DriverAdapter, build_vpnv4_adapter  # noqa: F401

__all__ = [
    "NamespaceDriver",
    "VPNv4DriverAdapter",
    "build_vpnv4_adapter",
]


