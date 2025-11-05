"""Driver adapters exposed to the minimal registry."""

from pkgutil import extend_path

__path__ = extend_path(__path__, __name__)

from .base import NamespaceDriver  # noqa: F401
from .vpnv4_adapter import VPNv4DriverAdapter, build_vpnv4_adapter  # noqa: F401

__all__ = [
    "NamespaceDriver",
    "VPNv4DriverAdapter",
    "build_vpnv4_adapter",
]


