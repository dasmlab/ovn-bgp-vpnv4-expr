#!/usr/bin/env python3
"""Ensure linux VRFs exist inside the FRR container for advertised tenants."""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_PATH = REPO_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from ovn_bgp_vpnv4.allocator import DeterministicAllocator  # noqa: E402


LOG = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tenants",
        type=Path,
        default=REPO_ROOT / "deploy/vpnv4/tenants.json",
        help="Path to tenants JSON definition",
    )
    parser.add_argument(
        "--container",
        default="frr-vpnv4",
        help="Name of the FRR container",
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


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    LOG.debug("Executing: %s", " ".join(cmd))
    return subprocess.run(cmd, check=False, text=True, capture_output=True)


def ensure_vrf(container: str, name: str, table_id: int) -> None:
    check = run(["docker", "exec", container, "ip", "link", "show", name])
    if check.returncode == 0:
        LOG.info("VRF '%s' already exists", name)
        return

    LOG.info("Creating VRF '%s' (table %s)", name, table_id)
    create = run(
        [
            "docker",
            "exec",
            container,
            "ip",
            "link",
            "add",
            name,
            "type",
            "vrf",
            "table",
            str(table_id),
        ]
    )
    if create.returncode != 0:
        LOG.error("Failed to create VRF %s: %s", name, create.stderr.strip())
        create.check_returncode()

    up = run(["docker", "exec", container, "ip", "link", "set", name, "up"])
    if up.returncode != 0:
        LOG.error("Failed to bring up VRF %s: %s", name, up.stderr.strip())
        up.check_returncode()


def ensure_blackhole_route(container: str, vrf: str, prefix: str) -> None:
    check = run(["docker", "exec", container, "ip", "route", "show", "vrf", vrf])
    if check.returncode == 0 and prefix in check.stdout:
        LOG.debug("Route %s already present in VRF '%s'", prefix, vrf)
        return

    LOG.info("Installing blackhole route %s in VRF '%s'", prefix, vrf)
    add = run(
        [
            "docker",
            "exec",
            container,
            "ip",
            "route",
            "add",
            "blackhole",
            prefix,
            "vrf",
            vrf,
        ]
    )
    if add.returncode != 0 and "File exists" not in add.stderr:
        LOG.error(
            "Failed to install blackhole route %s in VRF %s: %s",
            prefix,
            vrf,
            add.stderr.strip(),
        )
        add.check_returncode()


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)

    spec = load_spec(args.tenants)
    global_cfg = spec.get("global", {})
    rd_base = int(global_cfg.get("rd_base", global_cfg.get("local_asn", 65000)))
    rt_base = int(global_cfg.get("rt_base", global_cfg.get("local_asn", 65000)))
    allocator = DeterministicAllocator(rd_base=rd_base, rt_base=rt_base)

    for tenant in spec.get("tenants", []):
        namespace = tenant["namespace"]
        allocation = allocator.allocate(namespace)
        rd_id = int(allocation.rd.split(":", 1)[1])
        ensure_vrf(args.container, namespace, rd_id)
        for prefix in tenant.get("prefixes", []):
            ensure_blackhole_route(args.container, namespace, prefix)


if __name__ == "__main__":
    main()

