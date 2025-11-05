"""Minimal ovn-bgp-agent style integration helpers for the vpnv4 driver.

The real ovn-bgp-agent project provides a fairly involved driver registry and
event processing pipeline.  For the purposes of this repository we implement a
lightweight subset so the vpnv4 driver can be exercised end-to-end in tests and
lab environments without depending on the full agent source tree.
"""

from .events import NamespaceDelete, NamespaceUpsert  # noqa: F401
from .registry import DriverRegistry  # noqa: F401

__all__ = [
    "DriverRegistry",
    "NamespaceDelete",
    "NamespaceUpsert",
]


