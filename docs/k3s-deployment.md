# k3s Deployment Guide

This guide walks through deploying the VPNv4 driver on a k3s cluster with OVN-Kubernetes.

## Prerequisites

- k3s cluster (v1.28+) with OVN-Kubernetes CNI
- Access to FortiGate peers (or GoBGP simulator)
- Root/privileged access to nodes

### Setting Up k3s Cluster

If you need to set up a k3s cluster from scratch, see the [k3s Installation Guide](../../scripts/k3s-installation/README.md).

**Quick start:**
```bash
cd scripts/k3s-installation
./prepare-nodes.sh        # Prepare all nodes (hostname, prerequisites)
./install-k3s-cluster.sh  # Install k3s on all nodes
```

This will set up:
- Control node: `k3s-control` (10.20.1.100)
- Worker 1: `k3s-worker-1` (10.20.1.101)
- Worker 2: `k3s-worker-2` (10.20.1.102)

## Step 1: Load Kernel Modules

On each k3s node, load the required MPLS modules:

**Option 1: Use the provided script (recommended)**
```bash
# From scripts/k3s-installation directory
./load-mpls-modules.sh
```

**Option 2: Manual installation**
```bash
# Load modules immediately
sudo modprobe mpls_router mpls_iptunnel

# Make them persistent across reboots
cat <<EOF | sudo tee /etc/modules-load.d/mpls.conf
mpls_router
mpls_iptunnel
EOF

# Verify modules are loaded
lsmod | grep mpls
```

**Option 3: Systemd unit (if using deploy/k3s/00-mpls-modules.yaml)**
```bash
# Apply the systemd unit manifest
kubectl apply -f deploy/k3s/00-mpls-modules.yaml
```

## Step 2: Verify OVN-Kubernetes

Ensure OVN-Kubernetes is deployed and OVN NB DB is accessible:

```bash
# Check OVN pods
kubectl get pods -n ovn-kubernetes

# Verify OVN NB DB connectivity (from a node)
kubectl run -it --rm debug --image=ghcr.io/dasmlab/ovn-daemonset-fedora:dev --restart=Never -- bash
# Inside container:
# ovn-nbctl --db=tcp:127.0.0.1:6641 show
```

## Step 3: Configure Agent

Edit `deploy/k3s/vpnv4-agent.yaml` and update:

1. **Image:** Update `image:` field to your built image (or use pre-built from GHCR)
2. **FortiGate peer IPs:** Update `neighbours[].address` with your FortiGate IPs
3. **ASN configuration:** Adjust `local_asn`, `rd_base`, `rt_base` as needed
4. **OVN connection:** Update `watchers[].options.connection` if OVN NB DB is not on localhost

**Example configuration:**
```yaml
image: ghcr.io/dasmlab/vpnv4-agent:vpnv4-dev
# ... or build locally:
# image: ghcr.io/your-org/vpnv4-agent:vpnv4-dev
```

## Step 4: Deploy Agent

```bash
# Apply manifests
kubectl apply -f deploy/k3s/vpnv4-agent.yaml

# Check pods
kubectl get pods -n ovn-bgp-vpnv4 -w

# View logs
kubectl logs -n ovn-bgp-vpnv4 -l app=vpnv4-agent -f
```

## Step 5: Verify Deployment

```bash
# Check agent is running
kubectl get daemonset -n ovn-bgp-vpnv4

# Check VRF devices created
kubectl exec -n ovn-bgp-vpnv4 $(kubectl get pod -n ovn-bgp-vpnv4 -l app=vpnv4-agent -o jsonpath='{.items[0].metadata.name}') -- ip vrf show

# Check BGP sessions
kubectl exec -n ovn-bgp-vpnv4 $(kubectl get pod -n ovn-bgp-vpnv4 -l app=vpnv4-agent -o jsonpath='{.items[0].metadata.name}') -- vtysh -c "show bgp neighbors"

# Check VPNv4 routes
kubectl exec -n ovn-bgp-vpnv4 $(kubectl get pod -n ovn-bgp-vpnv4 -l app=vpnv4-agent -o jsonpath='{.items[0].metadata.name}') -- vtysh -c "show bgp ipv4 vpn"
```

## Step 6: Test with Namespaces

Create a test namespace and pod:

```bash
# Create namespace
kubectl create namespace test-vpnv4

# Create pod
kubectl run test-pod -n test-vpnv4 --image=busybox -- sleep 3600

# Wait for pod IP
kubectl get pod -n test-vpnv4 -o jsonpath='{.items[0].status.podIP}'

# Check if route was advertised
kubectl exec -n ovn-bgp-vpnv4 $(kubectl get pod -n ovn-bgp-vpnv4 -l app=vpnv4-agent -o jsonpath='{.items[0].metadata.name}') -- vtysh -c "show bgp ipv4 vpn" | grep <pod-ip>
```

## Troubleshooting

### Modules not loading

```bash
# Check kernel version
uname -r  # Must be 5.15+

# Check if modules exist
find /lib/modules/$(uname -r) -name "mpls*.ko"

# Check dmesg
dmesg | grep -i mpls
```

### Agent not starting

```bash
# Check logs
kubectl logs -n ovn-bgp-vpnv4 -l app=vpnv4-agent --previous

# Check events
kubectl get events -n ovn-bgp-vpnv4 --sort-by='.lastTimestamp'
```

### BGP session not established

```bash
# Check connectivity
kubectl exec -n ovn-bgp-vpnv4 <agent-pod> -- ping <fortigate-ip>

# Check firewall
sudo iptables -L | grep 179

# Check FRR config
kubectl exec -n ovn-bgp-vpnv4 <agent-pod> -- cat /etc/frr/vpnv4.conf
```

## Next Steps

- Test with real FortiGate appliances
- Validate bidirectional route exchange
- Monitor for stability
- Prepare for upstream integration

