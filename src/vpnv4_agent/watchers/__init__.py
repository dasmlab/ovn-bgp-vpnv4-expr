"""Watcher implementations used by the vpnv4 agent."""

from .file import FileNamespaceWatcher  # noqa: F401
from .ovn_nb import create_ovn_watcher  # noqa: F401

__all__ = ["FileNamespaceWatcher", "create_ovn_watcher"]


