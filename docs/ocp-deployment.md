# OpenShift Deployment Guide

This guide walks through deploying the VPNv4 driver on an OpenShift cluster with OVN-Kubernetes.

## Prerequisites

- OpenShift cluster (4.13+) with OVN-Kubernetes CNI
- Cluster admin access
- Access to FortiGate peers (or GoBGP simulator)
- Worker nodes must support kernel modules (standard RHCOS)

## Step 1: Load MPLS Kernel Modules

Apply the MachineConfig to load MPLS modules on all worker nodes:

```bash
# Apply MachineConfig
oc apply -f deploy/ocp/99-vpnv4-mpls-modules.yaml

# Wait for nodes to update (may trigger reboot)
oc get nodes -w

# Verify modules on a node
oc debug node/<worker-node-name>
# Inside debug shell:
chroot /host
lsmod | grep mpls
```

**Note:** The MachineConfig will cause worker nodes to reboot. Plan accordingly.

## Step 2: Verify OVN-Kubernetes

Ensure OVN-Kubernetes is deployed:

```bash
# Check OVN pods
oc get pods -n openshift-ovn-kubernetes

# Check OVN NB DB service
oc get svc -n openshift-ovn-kubernetes | grep ovnkube-db
```

## Step 3: Configure Agent

Edit `deploy/ocp/ovn-bgp-agent-config.yaml` and update:

1. **FortiGate peer IPs:** Update `neighbours[].address` with your FortiGate IPs
2. **ASN configuration:** Adjust `local_asn`, `rd_base`, `rt_base` as needed
3. **Namespace:** Update if using a different namespace (default: `openshift-ovn-kubernetes`)

## Step 4: Deploy Configuration

```bash
# Apply ConfigMap
oc apply -f deploy/ocp/ovn-bgp-agent-config.yaml

# Verify ConfigMap
oc get configmap ovn-bgp-agent-config -n openshift-ovn-kubernetes -o yaml
```

## Step 5: Patch DaemonSet

If `ovn-bgp-agent` DaemonSet already exists, patch it:

```bash
# Check existing DaemonSet
oc get daemonset ovn-bgp-agent -n openshift-ovn-kubernetes

# Apply patch
oc patch daemonset ovn-bgp-agent -n openshift-ovn-kubernetes --patch-file deploy/ocp/ovn-bgp-agent-daemonset-patch.yaml

# Or create new DaemonSet if it doesn't exist
oc apply -f deploy/ocp/ovn-bgp-agent-daemonset.yaml
```

**Note:** The patch references `quay.io/example/ovn-bgp-agent:vpnv4` - update this to your actual image location.

## Step 6: Build and Push Agent Image

Build the agent image and push to your registry:

```bash
# Build image
make agent-image IMAGE_TAG=quay.io/your-org/ovn-bgp-agent:vpnv4-dev

# Push image
make agent-push IMAGE_TAG=quay.io/your-org/ovn-bgp-agent:vpnv4-dev

# Update DaemonSet with correct image
oc set image daemonset/ovn-bgp-agent -n openshift-ovn-kubernetes ovn-bgp-agent=quay.io/your-org/ovn-bgp-agent:vpnv4-dev
```

## Step 7: Verify Deployment

```bash
# Check pods
oc get pods -n openshift-ovn-kubernetes -l app=ovn-bgp-agent

# Check logs
oc logs -n openshift-ovn-kubernetes -l app=ovn-bgp-agent -f

# Check VRF devices
oc exec -n openshift-ovn-kubernetes $(oc get pod -n openshift-ovn-kubernetes -l app=ovn-bgp-agent -o jsonpath='{.items[0].metadata.name}') -- ip vrf show

# Check BGP sessions
oc exec -n openshift-ovn-kubernetes $(oc get pod -n openshift-ovn-kubernetes -l app=ovn-bgp-agent -o jsonpath='{.items[0].metadata.name}') -- vtysh -c "show bgp neighbors"

# Check VPNv4 routes
oc exec -n openshift-ovn-kubernetes $(oc get pod -n openshift-ovn-kubernetes -l app=ovn-bgp-agent -o jsonpath='{.items[0].metadata.name}') -- vtysh -c "show bgp ipv4 vpn"
```

## Step 8: Test with Namespaces

Create a test namespace and pod:

```bash
# Create namespace
oc create namespace test-vpnv4

# Create pod
oc run test-pod -n test-vpnv4 --image=busybox -- sleep 3600

# Wait for pod IP
oc get pod -n test-vpnv4 -o jsonpath='{.items[0].status.podIP}'

# Check if route was advertised
oc exec -n openshift-ovn-kubernetes $(oc get pod -n openshift-ovn-kubernetes -l app=ovn-bgp-agent -o jsonpath='{.items[0].metadata.name}') -- vtysh -c "show bgp ipv4 vpn" | grep <pod-ip>
```

## Troubleshooting

### MachineConfig not applying

```bash
# Check MachineConfig status
oc get machineconfig 99-vpnv4-mpls-modules

# Check node conditions
oc get nodes -o yaml | grep -A 5 conditions

# Check MCO logs
oc logs -n openshift-machine-config-operator -l k8s-app=machine-config-operator
```

### Modules not loading

```bash
# Debug node
oc debug node/<worker-node-name>
chroot /host

# Check kernel version
uname -r

# Manually load modules
modprobe mpls_router
modprobe mpls_iptunnel

# Check dmesg
dmesg | grep -i mpls
```

### Agent not starting

```bash
# Check pod status
oc describe pod -n openshift-ovn-kubernetes -l app=ovn-bgp-agent

# Check events
oc get events -n openshift-ovn-kubernetes --sort-by='.lastTimestamp'

# Check image pull secrets
oc get secrets -n openshift-ovn-kubernetes | grep pull
```

### BGP session not established

```bash
# Check network policies
oc get networkpolicies -n openshift-ovn-kubernetes

# Check service connectivity
oc exec <agent-pod> -- ping <fortigate-ip>

# Check FRR logs
oc logs <agent-pod> | grep -i bgp
```

## Security Considerations

- Agent requires `hostNetwork: true` for BGP peering
- Ensure network policies allow BGP traffic (TCP 179)
- Image pull secrets may be required for private registries
- Service account may need additional RBAC permissions

## Next Steps

- Test with real FortiGate appliances
- Validate route exchange in production workloads
- Monitor for stability and performance
- Prepare for upstream integration

