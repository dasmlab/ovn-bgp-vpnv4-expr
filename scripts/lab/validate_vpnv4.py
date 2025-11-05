#!/usr/bin/env python3
"""Validate vpnv4 lab state after ``make lab-up``."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, Iterable


class ValidationError(RuntimeError):
    pass


def run(cmd: Iterable[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def docker_exec(container: str, *args: str) -> str:
    result = run(["docker", "exec", container, *args])
    if result.returncode != 0:
        raise ValidationError(
            f"docker exec {' '.join(args)} failed for {container}: {result.stderr.strip()}"
        )
    return result.stdout


def ensure_container_running(name: str) -> None:
    result = run(["docker", "inspect", "-f", "{{.State.Running}}", name])
    if result.returncode != 0 or result.stdout.strip().lower() != "true":
        raise ValidationError(f"container '{name}' is not running")


def load_tenants(tenants_file: Path) -> Dict[str, set[str]]:
    data = json.loads(tenants_file.read_text())
    return {
        tenant["namespace"]: set(tenant.get("prefixes", []))
        for tenant in data.get("tenants", [])
    }


def check_frr_summary(container: str, expected_prefixes: int) -> None:
    output = docker_exec(container, "vtysh", "-c", "show bgp ipv4 vpn summary json")
    summary = json.loads(output)
    peers = summary.get("peers", {})
    if not peers:
        raise ValidationError("FRR reports no vpnv4 peers")

    peer = next(iter(peers.values()))
    state = peer.get("state")
    if state != "Established":
        raise ValidationError(f"FRR peer not established (state={state!r})")

    if peer.get("pfxSnt", 0) < expected_prefixes:
        raise ValidationError(
            f"FRR advertised {peer.get('pfxSnt', 0)} prefixes, expected >= {expected_prefixes}"
        )


def check_gobgp_neighbor(container: str) -> None:
    output = docker_exec(container, "gobgp", "neighbor", "-j")
    neighbors = json.loads(output)
    if not neighbors:
        raise ValidationError("GoBGP reports no neighbors")
    state = neighbors[0].get("state", {}).get("session_state")
    if state != 6:  # Established
        raise ValidationError(f"GoBGP neighbor not established (state={state})")


def check_gobgp_vrfs(container: str, expected: Dict[str, set[str]]) -> None:
    for namespace, prefixes in expected.items():
        output = docker_exec(container, "gobgp", "vrf", namespace, "rib", "-j")
        rib = json.loads(output or "{}")
        observed_keys = set(rib.keys()) if isinstance(rib, dict) else set()
        # rib keys include RD prefix, e.g. "65000:10903:10.244.0.0/24"
        cleaned = {key.split(":", 2)[-1] for key in observed_keys}
        missing = prefixes - cleaned
        if missing:
            raise ValidationError(
                f"GoBGP missing prefixes for {namespace}: {', '.join(sorted(missing))}"
            )


def check_kernel_routes(container: str, expected: Dict[str, set[str]]) -> None:
    for namespace, prefixes in expected.items():
        if not prefixes:
            continue
        output = docker_exec(container, "ip", "route", "show", "vrf", namespace)
        for prefix in prefixes:
            if prefix not in output:
                raise ValidationError(
                    f"Kernel VRF {namespace} missing route for {prefix}"
                )


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    tenants_file = Path(
        os.environ.get("TENANTS_FILE", repo_root / "deploy/vpnv4/tenants.json")
    )
    if not tenants_file.exists():
        raise SystemExit(f"tenants definition not found: {tenants_file}")

    tenants = load_tenants(tenants_file)
    total_prefixes = sum(len(pfx) for pfx in tenants.values())

    frr_container = os.environ.get("FRR_CONTAINER", "frr-vpnv4")
    gobgp_container = os.environ.get("GOBGP_CONTAINER", "gobgp-fortigate-sim")

    ensure_container_running(frr_container)
    ensure_container_running(gobgp_container)

    check_frr_summary(frr_container, total_prefixes)
    check_gobgp_neighbor(gobgp_container)
    check_gobgp_vrfs(gobgp_container, tenants)
    check_kernel_routes(frr_container, tenants)

    print("vpnv4 lab validation succeeded")


if __name__ == "__main__":
    try:
        main()
    except ValidationError as exc:
        print(f"[validate_vpnv4] ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

