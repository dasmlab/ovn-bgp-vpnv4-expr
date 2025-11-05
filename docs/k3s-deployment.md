# k3s Deployment Guide

This guide walks through deploying the VPNv4 driver on a k3s cluster with OVN-Kubernetes.

## Prerequisites

- k3s cluster (v1.28+) with OVN-Kubernetes CNI
- Access to FortiGate peers (or GoBGP simulator)
- Root/privileged access to nodes

## Step 1: Load Kernel Modules

On each k3s node, load the required MPLS modules:

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

Alternatively, use the systemd unit approach:

```bash
# Create systemd service
sudo tee /etc/systemd/system/mpls-modules.service <<EOF
[Unit]
Description=Load MPLS modules for VPNv4 driver
After=network.target

[Service]
Type=oneshot
ExecStart=/usr/sbin/modprobe mpls_router
ExecStart=/usr/sbin/modprobe mpls_iptunnel
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

# Enable and start
sudo systemctl enable mpls-modules.service
sudo systemctl start mpls-modules.service
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

1. **FortiGate peer IPs:** Update `neighbours[].address` with your FortiGate IPs
2. **ASN configuration:** Adjust `local_asn`, `rd_base`, `rt_base` as needed
3. **OVN connection:** Update `watchers[].options.connection` if OVN NB DB is not on localhost

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

