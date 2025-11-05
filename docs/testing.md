# Testing Guide for VPNv4 Driver

This guide outlines the testing procedures for validating the VPNv4 driver on production-like clusters (k3s or OpenShift) before upstream integration.

## Pre-Testing Checklist

- [ ] Cluster is deployed with OVN-Kubernetes
- [ ] Kernel modules (`mpls_router`, `mpls_iptunnel`) are loaded on all nodes
- [ ] VPNv4 agent is deployed and running
- [ ] FortiGate peers are configured and reachable
- [ ] BGP sessions are established

## Test Scenarios

### 1. Basic Route Advertisement

**Objective:** Verify that pod IPs are advertised via VPNv4 to FortiGate peers.

**Steps:**
1. Create a test namespace:
   ```bash
   kubectl create namespace test-vpnv4-1
   ```

2. Create a pod:
   ```bash
   kubectl run test-pod-1 -n test-vpnv4-1 --image=busybox -- sleep 3600
   ```

3. Wait for pod IP assignment:
   ```bash
   kubectl get pod -n test-vpnv4-1 -o jsonpath='{.items[0].status.podIP}'
   ```

4. Verify route advertisement:
   ```bash
   # On agent node
   kubectl exec -n <agent-namespace> <agent-pod> -- vtysh -c "show bgp ipv4 vpn" | grep <pod-ip>
   
   # On FortiGate (or GoBGP simulator)
   gobgp global rib -a vpnv4 | grep <pod-ip>
   ```

**Expected Result:** Route appears in both FRR and FortiGate with correct RD/RT.

### 2. Multi-Namespace Support

**Objective:** Verify that multiple namespaces get distinct VRFs and RD/RT allocations.

**Steps:**
1. Create multiple namespaces with pods:
   ```bash
   for ns in test-a test-b test-c; do
     kubectl create namespace $ns
     kubectl run pod-$ns -n $ns --image=busybox -- sleep 3600
   done
   ```

2. Verify distinct VRFs:
   ```bash
   kubectl exec <agent-pod> -- ip vrf show
   ```

3. Verify distinct RDs:
   ```bash
   kubectl exec <agent-pod> -- vtysh -c "show bgp ipv4 vpn" | grep "Route Distinguisher"
   ```

**Expected Result:** Each namespace has its own VRF and unique RD/RT.

### 3. Route Withdrawal

**Objective:** Verify that routes are withdrawn when pods are deleted.

**Steps:**
1. Note the pod IP from test scenario 1
2. Delete the pod:
   ```bash
   kubectl delete pod test-pod-1 -n test-vpnv4-1
   ```

3. Verify route withdrawal:
   ```bash
   # Wait for BGP update (typically 30-60 seconds)
   sleep 60
   
   # Check route is gone
   kubectl exec <agent-pod> -- vtysh -c "show bgp ipv4 vpn" | grep <pod-ip>
   ```

**Expected Result:** Route is withdrawn from both FRR and FortiGate.

### 4. Namespace Deletion

**Objective:** Verify that VRF is cleaned up when namespace is deleted.

**Steps:**
1. Delete a namespace:
   ```bash
   kubectl delete namespace test-vpnv4-1
   ```

2. Verify VRF cleanup:
   ```bash
   kubectl exec <agent-pod> -- ip vrf show
   kubectl exec <agent-pod> -- vtysh -c "show bgp vrf all"
   ```

**Expected Result:** VRF and associated routes are removed.

### 5. Bidirectional Route Exchange

**Objective:** Verify that routes advertised from FortiGate are received and installed.

**Steps:**
1. On FortiGate, advertise a test route:
   ```bash
   # Using GoBGP simulator
   gobgp vrf add test-vrf rd 65100:100 rt both 65100:100
   gobgp vrf test-vrf rib add 192.168.100.0/24
   ```

2. Verify route import on agent:
   ```bash
   kubectl exec <agent-pod> -- vtysh -c "show bgp ipv4 vpn" | grep 192.168.100.0/24
   ```

3. Check kernel route:
   ```bash
   kubectl exec <agent-pod> -- ip route show vrf <vrf-name>
   ```

**Expected Result:** Route is imported and installed in the appropriate VRF.

### 6. Real-Time Updates

**Objective:** Verify that agent responds to namespace/pod changes in real-time.

**Steps:**
1. Monitor agent logs:
   ```bash
   kubectl logs -n <agent-namespace> -l app=vpnv4-agent -f
   ```

2. Create a new namespace and pod:
   ```bash
   kubectl create namespace test-realtime
   kubectl run test-realtime-pod -n test-realtime --image=busybox -- sleep 3600
   ```

3. Observe logs for namespace detection and route advertisement

**Expected Result:** Agent detects namespace within polling interval (default 5s) and advertises route.

### 7. High Availability

**Objective:** Verify agent behavior during node failures.

**Steps:**
1. Identify node running agent pod
2. Cordon and drain the node:
   ```bash
   kubectl cordon <node-name>
   kubectl drain <node-name> --ignore-daemonsets --delete-emptydir-data
   ```

3. Verify agent reschedules:
   ```bash
   kubectl get pods -n <agent-namespace> -o wide
   ```

4. Verify BGP sessions re-establish:
   ```bash
   kubectl exec <new-agent-pod> -- vtysh -c "show bgp neighbors"
   ```

**Expected Result:** Agent reschedules and BGP sessions re-establish.

### 8. Scale Testing

**Objective:** Verify behavior with many namespaces and routes.

**Steps:**
1. Create many namespaces:
   ```bash
   for i in {1..50}; do
     kubectl create namespace scale-test-$i
     kubectl run pod-$i -n scale-test-$i --image=busybox -- sleep 3600
   done
   ```

2. Monitor agent performance:
   ```bash
   kubectl top pod -n <agent-namespace>
   ```

3. Verify all routes advertised:
   ```bash
   kubectl exec <agent-pod> -- vtysh -c "show bgp ipv4 vpn summary"
   ```

**Expected Result:** Agent handles scale without performance degradation.

## Validation Scripts

### Automated Validation

Create a validation script:

```bash
#!/bin/bash
# scripts/validate-production.sh

set -e

echo "=== VPNv4 Driver Production Validation ==="

# Check kernel modules
echo "1. Checking kernel modules..."
kubectl exec <agent-pod> -- lsmod | grep mpls || exit 1

# Check agent pods
echo "2. Checking agent pods..."
kubectl get pods -n <agent-namespace> -l app=vpnv4-agent | grep Running || exit 1

# Check BGP sessions
echo "3. Checking BGP sessions..."
kubectl exec <agent-pod> -- vtysh -c "show bgp neighbors" | grep Established || exit 1

# Check VRFs
echo "4. Checking VRFs..."
vrf_count=$(kubectl exec <agent-pod> -- ip vrf show | wc -l)
if [ $vrf_count -lt 1 ]; then
  echo "ERROR: No VRFs found"
  exit 1
fi

# Check routes
echo "5. Checking VPNv4 routes..."
route_count=$(kubectl exec <agent-pod> -- vtysh -c "show bgp ipv4 vpn" | grep -c "Network" || echo "0")
if [ $route_count -lt 1 ]; then
  echo "WARNING: No VPNv4 routes found"
fi

echo "=== Validation Complete ==="
```

## Performance Benchmarks

### Baseline Metrics

- **Route advertisement latency:** < 5 seconds from pod creation
- **Route withdrawal latency:** < 60 seconds from pod deletion
- **Memory usage:** < 512Mi per agent pod
- **CPU usage:** < 500m per agent pod
- **BGP session establishment:** < 30 seconds after agent start

### Monitoring

Set up Prometheus metrics (if available):

```bash
# Check agent metrics endpoint
kubectl port-forward <agent-pod> 8080:8080
curl http://localhost:8080/metrics
```

## Failure Scenarios

### Agent Pod Crash

1. Delete agent pod:
   ```bash
   kubectl delete pod <agent-pod> -n <agent-namespace>
   ```

2. Verify restart:
   ```bash
   kubectl get pods -n <agent-namespace> -w
   ```

3. Verify BGP sessions re-establish

### OVN NB DB Unavailable

1. Simulate OVN NB DB failure
2. Verify agent logs error handling
3. Verify agent continues operating with cached state

### FortiGate Peer Unreachable

1. Block BGP traffic (firewall rule)
2. Verify agent logs connection attempts
3. Verify routes remain in FRR table
4. Restore connectivity and verify session re-establishment

## Reporting

Document test results:

- Test environment (k3s/OCP version, node count, etc.)
- Test scenarios executed
- Results (pass/fail with details)
- Performance metrics
- Issues encountered and resolutions

## Next Steps After Testing

- Fix any issues found
- Re-test fixed scenarios
- Document workarounds
- Prepare test report for upstream PR

