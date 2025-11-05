# Cluster Setup Requirements for VPNv4 Driver

## Overview

This document describes the system under test (SUT) requirements for deploying the OVN-BGP VPNv4 driver on production-like clusters (k3s or OpenShift). The driver requires specific kernel modules, node configurations, and network prerequisites.

## Prerequisites

### 1. Cluster Requirements

- **Kubernetes version:** 1.28+ (k3s) or OpenShift 4.13+
- **CNI:** OVN-Kubernetes (required)
- **Node OS:** Linux kernel 5.15+ (Ubuntu 22.04+, RHEL 8.5+, or equivalent)
- **Network connectivity:** Nodes must have IP reachability to FortiGate peers

### 2. Kernel Modules

The VPNv4 driver requires MPLS kernel modules to be loaded on all worker nodes, even though we're not doing full MPLS forwarding. These modules are needed for the kernel to accept MPLS-labeled next-hops.

**Required modules:**
- `mpls_router`
- `mpls_iptunnel`

**Load on boot:**
- On k3s: Use `modprobe.d` or systemd units
- On OpenShift: Use MachineConfig (see `deploy/ocp/99-vpnv4-mpls-modules.yaml`)

### 3. Network Prerequisites

- **BGP peering:** Worker nodes must have IP connectivity to FortiGate peers
- **Routing:** BGP sessions run over IP (no MPLS transport required)
- **VRF support:** Linux kernel must support VRF devices (kernel 4.3+)

### 4. OVN-Kubernetes Configuration

- OVN-Kubernetes must be deployed and operational
- OVN Northbound DB must be accessible (default: `tcp:127.0.0.1:6641` or via service)
- Logical switch ports must have proper external IDs for namespace extraction

## Deployment Options

### Option 1: k3s Cluster

See `docs/k3s-deployment.md` for step-by-step instructions.

**Quick start:**
```bash
# 1. Install k3s
curl -sfL https://get.k3s.io | sh -

# 2. Load kernel modules
sudo modprobe mpls_router mpls_iptunnel
echo "mpls_router" | sudo tee -a /etc/modules-load.d/mpls.conf
echo "mpls_iptunnel" | sudo tee -a /etc/modules-load.d/mpls.conf

# 3. Deploy OVN-Kubernetes
kubectl apply -f deploy/ovn/...

# 4. Apply VPNv4 agent
kubectl apply -f deploy/k3s/vpnv4-agent.yaml
```

### Option 2: OpenShift Cluster

See `docs/ocp-deployment.md` for step-by-step instructions.

**Quick start:**
```bash
# 1. Apply MachineConfig for kernel modules
oc apply -f deploy/ocp/99-vpnv4-mpls-modules.yaml

# 2. Wait for nodes to reboot/update
oc get nodes -w

# 3. Apply ConfigMap
oc apply -f deploy/ocp/ovn-bgp-agent-config.yaml

# 4. Patch DaemonSet
oc patch daemonset ovn-bgp-agent -n ovn-kubernetes --patch-file deploy/ocp/ovn-bgp-agent-daemonset-patch.yaml
```

## Configuration

### Agent Configuration

The VPNv4 agent requires a ConfigMap with the following structure:

```yaml
driver:
  local_asn: 65000
  router_id: 10.255.0.2
  rd_base: 65000
  rt_base: 65000
  maintain_empty_vrf: true
  neighbours:
    - address: <fortigate-ip>
      remote_asn: <fortigate-asn>
      families: [vpnv4]

watchers:
  - type: ovn
    options:
      connection: tcp:127.0.0.1:6641  # Or OVN NB service endpoint
      interval: 5
```

### FortiGate Configuration

FortiGate peers must be configured with:
- VPNv4 address family enabled
- Route target import/export policies matching your RT allocation
- BGP session to agent nodes

## Validation

After deployment, verify:

1. **Kernel modules loaded:**
   ```bash
   lsmod | grep mpls
   ```

2. **Agent pods running:**
   ```bash
   kubectl get pods -n ovn-kubernetes -l app=ovn-bgp-agent
   ```

3. **VRF devices created:**
   ```bash
   kubectl exec -n ovn-kubernetes <agent-pod> -- ip vrf show
   ```

4. **BGP sessions established:**
   ```bash
   kubectl exec -n ovn-kubernetes <agent-pod> -- vtysh -c "show bgp neighbors"
   ```

5. **Routes advertised:**
   ```bash
   kubectl exec -n ovn-kubernetes <agent-pod> -- vtysh -c "show bgp ipv4 vpn"
   ```

## Troubleshooting

### Module not loading

- Check kernel version: `uname -r` (must be 5.15+)
- Verify module exists: `find /lib/modules/$(uname -r) -name mpls_router.ko`
- Check dmesg for errors: `dmesg | grep mpls`

### BGP session not established

- Verify network connectivity: `ping <fortigate-ip>`
- Check firewall rules (BGP uses TCP 179)
- Verify ASN configuration matches

### Routes not appearing

- Check OVN watcher connectivity: `kubectl logs <agent-pod> | grep OVN`
- Verify namespace discovery: `kubectl logs <agent-pod> | grep namespace`
- Check FRR config: `kubectl exec <agent-pod> -- cat /etc/frr/vpnv4.conf`

## Next Steps

After successful deployment:
1. Test with real FortiGate appliances
2. Validate route exchange in both directions
3. Test namespace creation/deletion
4. Monitor for stability over extended periods

See `docs/testing.md` for detailed testing procedures.

