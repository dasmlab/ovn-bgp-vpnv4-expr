"""YAML configuration loader for the vpnv4 agent."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Sequence

import yaml

from ovn_bgp_vpnv4.config import AddressFamily, GlobalConfig, Neighbor


@dataclass
class DriverConfig:
    local_asn: int
    router_id: str
    rd_base: int
    rt_base: int
    neighbours: Sequence[Neighbor]
    output_dir: Path
    include_globals: bool = False
    export_ipv6: bool = False
    maintain_empty_vrf: bool = True

    def to_global_config(self) -> GlobalConfig:
        return GlobalConfig(
            local_asn=self.local_asn,
            router_id=self.router_id,
            rd_base=self.rd_base,
            rt_base=self.rt_base,
            neighbours=self.neighbours,
            export_ipv6=self.export_ipv6,
        )


@dataclass
class WatcherConfig:
    type: str
    path: Path
    interval: float = 5.0
    options: dict = field(default_factory=dict)


@dataclass
class AgentConfig:
    driver: DriverConfig
    watchers: Sequence[WatcherConfig] = field(default_factory=list)


def _parse_neighbor(entry: dict) -> Neighbor:
    families_raw: Iterable[str] | None = entry.get("families")
    if families_raw:
        families = []
        for fam in families_raw:
            fam_upper = fam.upper()
            if fam_upper == "VPNV4":
                families.append(AddressFamily.VPNV4)
            elif fam_upper == "VPNV6":
                families.append(AddressFamily.VPNV6)
            else:
                raise ValueError(f"Unsupported address family '{fam}'")
        families_tuple: Sequence[AddressFamily] = tuple(families)
    else:
        families_tuple = (AddressFamily.VPNV4,)

    return Neighbor(
        address=str(entry["address"]),
        remote_asn=int(entry["remote_asn"]),
        families=families_tuple,
        description=entry.get("description"),
    )


def _parse_driver(section: dict) -> DriverConfig:
    neighbours_data = section.get("neighbours", [])
    neighbours: List[Neighbor] = [
        _parse_neighbor(neigh) for neigh in neighbours_data
    ]
    output_dir = Path(section.get("output_dir", "/etc/frr"))

    return DriverConfig(
        local_asn=int(section["local_asn"]),
        router_id=str(section["router_id"]),
        rd_base=int(section.get("rd_base", section["local_asn"])),
        rt_base=int(section.get("rt_base", section["local_asn"])),
        neighbours=neighbours,
        output_dir=output_dir,
        include_globals=bool(section.get("include_globals", False)),
        export_ipv6=bool(section.get("export_ipv6", False)),
        maintain_empty_vrf=bool(section.get("maintain_empty_vrf", True)),
    )
def _parse_watchers(entries: Iterable[dict]) -> List[WatcherConfig]:
    watchers: List[WatcherConfig] = []
    for entry in entries:
        options = entry.get("options", {})
        if not isinstance(options, dict):
            raise ValueError("watcher 'options' must be a mapping if provided")
        watchers.append(
            WatcherConfig(
                type=str(entry["type"]),
                path=Path(entry.get("path", ".")),
                interval=float(entry.get("interval", entry.get("poll_interval", 5.0))),
                options=options,
            )
        )
    return watchers


def load_config(path: Path) -> AgentConfig:
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict):
        raise ValueError("Agent configuration must be a mapping")

    driver_section = data.get("driver")
    if driver_section is None:
        raise ValueError("Configuration missing 'driver' section")
    driver = _parse_driver(driver_section)

    watchers_section = data.get("watchers", [])
    if not isinstance(watchers_section, list):
        raise ValueError("'watchers' section must be a list")
    watchers = _parse_watchers(watchers_section)

    return AgentConfig(driver=driver, watchers=watchers)


