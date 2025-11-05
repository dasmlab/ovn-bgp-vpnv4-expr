# Project Task Board — OVN-BGP VPNv4 Experiment

This file expands the backlog from the README into actionable work items grouped by milestones. Update status markers (`☐`, `🏗`, `✅`) as work progresses.

## Milestone 0 — Design Readiness

| Status | Task | Owner | Notes |
|--------|------|-------|-------|
| ✅ | Capture baseline design + rationale | DASM | README section 1–3 complete |
| ☐ | Finalize RD/RT allocation policy | TBD | Define deterministic mapping, persistence |
| ☐ | Document simulator requirements | TBD | Input/output schema, APIs, failure modes |
| ☐ | Decide FRR integration surface | TBD | vtysh CLI vs. frr-reload.py vs. gRPC northbound |
| ☐ | Validate MPLS kernel module requirements | TBD | Confirm `mpls_router`/`mpls_iptunnel` necessity |

## Milestone 1 — Lab Toolchain

| Status | Task | Owner | Notes |
|--------|------|-------|-------|
| ☐ | Scaffold `docker-compose` topology (FRR + simulator) | TBD | Include health-check scripts |
| ☐ | Author `scripts/lab/` helpers (`lab-up`, `lab-down`) | TBD | Parameterize for CI |
| ☐ | Create `make` targets (`deps`, `lab-up`, `test`, `observe`) | TBD | Align with README workflow |
| ☐ | Produce network diagram & document in `docs/lab-topology.md` | TBD | Use ASCII or draw.io |
| ☐ | Integrate kernel module loading into `lab-up.sh` | TBD | Execute `modprobe` + verification |

## Milestone 2 — VPNv4 Driver Prototype

| Status | Task | Owner | Notes |
|--------|------|-------|-------|
| ☐ | Add feature flag to select vpnv4 mode | TBD | Env var or config file |
| ☐ | Implement RD/RT allocator module | TBD | Includes unit tests |
| ☐ | Generate FRR VRF stanzas per namespace | TBD | Ensure idempotent rendering |
| ☐ | Export prefixes via vpnv4 AF | TBD | Validate with simulator |

## Milestone 3 — Testing & Observability

| Status | Task | Owner | Notes |
|--------|------|-------|-------|
| ☐ | Build pytest/go integration harness | TBD | Talks to simulator API |
| ☐ | Capture baseline metrics (Prometheus/OpenMetrics) | TBD | Add new counters if needed |
| ☐ | Automate packet capture workflow | TBD | Use tcpdump container sidecar |
| ☐ | Integrate tests into CI pipeline | TBD | GitHub Actions/GitLab template |
| ☐ | Add pre-flight check for MPLS modules in tests | TBD | Fail fast with actionable guidance |

## Milestone 4 — Hardware Validation (Stretch)

| Status | Task | Owner | Notes |
|--------|------|-------|-------|
| ☐ | Secure FortiGate lab appliance or VM | TBD | Licensing, access planning |
| ☐ | Replicate simulator automation against hardware | TBD | Adjust CLI adapter |
| ☐ | Document operational runbook | TBD | Day-2 troubleshooting |

---

_Last updated: 2025-10-31_

