from __future__ import annotations

import ipaddress
from typing import Mapping, Optional


NAMESPACE_KEYS = (
    "k8s.ovn.org/namespace",
    "k8s.ovn.org/project",
    "neutron:project_id",
    "namespace",
    "name",
)


def namespace_from_external_ids(external_ids: Mapping[str, str]) -> Optional[str]:
    for key in NAMESPACE_KEYS:
        value = external_ids.get(key)
        if value:
            return value
    return None


def normalize_prefix(value: str) -> str:
    if not value:
        raise ValueError("Prefix value cannot be empty")
    if "/" in value:
        return value
    ip = ipaddress.ip_address(value)
    if ip.version == 4:
        return f"{value}/32"
    return f"{value}/128"


