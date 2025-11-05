"""Driver adapters exposed to the minimal registry and upstream agent."""

from pkgutil import extend_path

__path__ = extend_path(__path__, __name__)

from .base import NamespaceDriver  # noqa: F401
from .vpnv4_adapter import VPNv4DriverAdapter, build_vpnv4_adapter  # noqa: F401

# Upstream driver for stevedore entry point
try:
    from .upstream_vpnv4_driver import VPNv4UpstreamDriver  # noqa: F401
    __all__ = [
        "NamespaceDriver",
        "VPNv4DriverAdapter",
        "build_vpnv4_adapter",
        "VPNv4UpstreamDriver",
    ]
except ImportError:
    # Upstream driver may not be fully implemented yet
    __all__ = [
        "NamespaceDriver",
        "VPNv4DriverAdapter",
        "build_vpnv4_adapter",
    ]


