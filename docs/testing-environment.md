# Testing & POC Environment Guide

## 1. Purpose

Document the repeatable lab used to validate the OVN-BGP VPNv4 driver against a simulated FortiGate peer. This guide enumerates dependencies, bootstrap steps, and teardown procedures so contributors can reproduce results locally or in CI.

## 2. Prerequisites

- Linux host with virtualization enabled (tested on Ubuntu 22.04, kernel ≥ 5.15).
- Docker 24.x or Podman 4.x with Compose plugin.
- `kind` ≥ 0.22, `kubectl` ≥ 1.29.
- Python 3.10+ and Go 1.21+ for testing harnesses.
- Optional: tshark/wireshark for packet captures.
- Ability to load Linux kernel modules `mpls_router` and `mpls_iptunnel` (even if label switching stays disabled).

## 3. Environment Variables

Create `scripts/lab/env.example` (future task) with the following template:

```
# BGP identifiers
LAB_LOCAL_ASN=65000
LAB_REMOTE_ASN=65100
LAB_ROUTER_ID_PREFIX=10.255.0

# Networking
LAB_PEERING_SUBNET=172.31.0.0/24
LAB_KIND_NETWORK=ovn-bgp-lab

# Paths
LAB_ARTIFACT_DIR=${PWD}/artifacts
```

Contributors copy this file to `scripts/lab/.env` and adjust values for their setup.

## 4. Bootstrap Workflow (Draft)

1. `make deps`
   - Installs binaries via `hack/install-tools.sh` (to be authored).
2. `make lab-up`
   - Creates kind cluster.
   - Deploys OVN-Kubernetes manifests.
   - Launches FRR + FortiGate simulator via Compose.
   - Applies generated FRR configs from `deploy/frr/`.
   - Loads required kernel modules via `modprobe mpls_router mpls_iptunnel` (if not already present).
3. `make test`
   - Runs unit tests (pytest/go) and integration suite hitting simulator API.
4. `make observe`
   - Captures BGP tables, Prometheus metrics, and pcaps into `artifacts/`.
5. `make lab-down`
   - Destroys containers and kind cluster, cleans temps.

## 5. CI Considerations

- Prefer GitHub Actions self-hosted runners for access to Docker-in-Docker and kernel features.
- Cache Docker images (`frrouting/frr`, `gobgp/gobgp`) to reduce setup time.
- Gate merges on `make test`; optionally run `make lab-up && make observe` only on nightly jobs due to runtime.

## 6. Safety & Cleanup

- Ensure `make lab-down` is idempotent; include safeguards for accidental deletion (prompt before destroying non-lab Docker networks).
- Prune stale Compose networks to avoid conflicts between runs.
- Collect logs before teardown to aid debugging (`scripts/lab/collect-logs.sh`, future task).

### 6.1 Kernel Module Checklist

1. `sudo modprobe mpls_router mpls_iptunnel` — load modules (wrapped by `lab-up.sh`).
2. `lsmod | grep mpls` — confirm modules are resident.
3. `sudo sysctl net.mpls.platform_labels` — ensure value is 0 unless testing label switching.
4. If modules are unavailable (e.g., minimal VM kernel), skip dataplane-validation tests and note limitation in test report.

## 7. Future Enhancements

- Parameterize lab to run multiple VRFs simultaneously.
- Introduce optional MPLS dataplane tests behind feature flag.
- Add Vagrant/Ansible recipe for bare-metal staging environments.

