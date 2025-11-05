#!/usr/bin/env python3
"""Render vpnv4 FRR configuration using the experimental driver."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_PATH = REPO_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from ovn_bgp_vpnv4.config import (  # noqa: E402
    AddressFamily,
    GlobalConfig,
    Neighbor,
)
from ovn_bgp_vpnv4.driver import VPNv4RouteDriver  # noqa: E402


LOG = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tenants",
        type=Path,
        default=Path("deploy/vpnv4/tenants.json"),
        help="Path to tenants JSON definition",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("deploy/frr"),
        help="Directory where vpnv4.conf will be written",
    )
    parser.add_argument(
        "--base-config",
        type=Path,
        default=Path("deploy/frr/frr.conf"),
        help="Base FRR configuration to merge with vpnv4 output",
    )
    parser.add_argument(
        "--include-globals",
        action="store_true",
        help="Render global BGP configuration as well (overrides base frr.conf)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    return parser.parse_args()


def load_spec(path: Path) -> Dict[str, Any]:
    with path.open() as fh:
        return json.load(fh)


def build_global_config(config: Dict[str, Any]) -> GlobalConfig:
    neighbours = [
        Neighbor(
            address=n["address"],
            remote_asn=int(n["remote_asn"]),
            families=_parse_families(n.get("families")),
            description=n.get("description"),
        )
        for n in config.get("neighbors", [])
    ]

    return GlobalConfig(
        local_asn=int(config["local_asn"]),
        router_id=config["router_id"],
        rd_base=int(config.get("rd_base", config["local_asn"])),
        rt_base=int(config.get("rt_base", config["local_asn"])),
        neighbours=neighbours,
        export_ipv6=config.get("export_ipv6", False),
    )


def _parse_families(values: Iterable[str] | None) -> Sequence[AddressFamily]:
    if not values:
        return (AddressFamily.VPNV4,)
    mapping = {"VPNV4": AddressFamily.VPNV4, "VPNV6": AddressFamily.VPNV6}
    resolved = []
    for value in values:
        key = value.upper()
        if key not in mapping:
            raise ValueError(f"Unsupported address family '{value}'")
        resolved.append(mapping[key])
    return tuple(resolved)


def merge_configs(base_path: Path, vpnv4_path: Path, output_path: Path) -> None:
    base_content = base_path.read_text().rstrip()
    vpnv4_content = vpnv4_path.read_text().strip() if vpnv4_path.exists() else ""

    parts = [base_content]
    if vpnv4_content:
        parts.extend([
            "",
            "! --- vpnv4 auto-generated section ---",
            vpnv4_content,
            "! --- end vpnv4 auto-generated section ---",
            "",
        ])

    merged = "\n".join(parts) + "\n"
    output_path.write_text(merged)
    LOG.info("Merged config written to %s", output_path)


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)

    spec = load_spec(args.tenants)
    global_cfg = build_global_config(spec["global"])

    driver = VPNv4RouteDriver(
        config=global_cfg,
        output_dir=args.output_dir,
        include_globals=args.include_globals,
    )

    for tenant in spec.get("tenants", []):
        namespace = tenant["namespace"]
        prefixes = tenant.get("prefixes", [])
        if not prefixes:
            LOG.warning("Tenant %s has no prefixes defined", namespace)
        driver.advertise_prefixes(namespace, prefixes)

    rendered = driver.get_rendered_config()
    vpnv4_path = args.output_dir / "vpnv4.conf"
    if rendered:
        LOG.info("Rendered vpnv4 config written to %s", vpnv4_path)
    else:
        LOG.warning("No config was rendered (check tenant definitions)")

    merge_configs(args.base_config, vpnv4_path, args.output_dir / "frr.merged.conf")


if __name__ == "__main__":
    main()

