#!/usr/bin/env bash
# Verify k3s cluster is ready
# Usage: ./verify-cluster.sh [kubeconfig-path]
# Example: ./verify-cluster.sh ~/.kube/config

set -euo pipefail

KUBECONFIG="${1:-${KUBECONFIG:-$HOME/.kube/config}}"

if [ ! -f "$KUBECONFIG" ]; then
    echo "ERROR: Kubeconfig not found: $KUBECONFIG"
    echo "Usage: $0 [kubeconfig-path]"
    echo "Or set KUBECONFIG environment variable"
    exit 1
fi

export KUBECONFIG

echo "[verify] Verifying k3s cluster..."
echo "[verify] Using kubeconfig: $KUBECONFIG"
echo ""

# Check kubectl access
if ! kubectl cluster-info >/dev/null 2>&1; then
    echo "[verify] ERROR: Cannot access cluster"
    exit 1
fi

echo "[verify] ✓ Cluster is accessible"
echo ""

# Check nodes
echo "[verify] Checking nodes..."
NODES=$(kubectl get nodes --no-headers 2>/dev/null | wc -l)
if [ "$NODES" -lt 1 ]; then
    echo "[verify] ERROR: No nodes found"
    exit 1
fi

kubectl get nodes
echo ""

# Check node readiness
NOT_READY=$(kubectl get nodes --no-headers 2>/dev/null | grep -v " Ready " | wc -l)
if [ "$NOT_READY" -gt 0 ]; then
    echo "[verify] WARNING: Some nodes are not Ready"
    kubectl get nodes
else
    echo "[verify] ✓ All nodes are Ready"
fi
echo ""

# Check OVN-Kubernetes
echo "[verify] Checking OVN-Kubernetes..."
if kubectl get namespace ovn-kubernetes >/dev/null 2>&1; then
    OVN_PODS=$(kubectl get pods -n ovn-kubernetes --no-headers 2>/dev/null | wc -l)
    if [ "$OVN_PODS" -gt 0 ]; then
        echo "[verify] ✓ OVN-Kubernetes namespace exists"
        echo "[verify] OVN pods:"
        kubectl get pods -n ovn-kubernetes
    else
        echo "[verify] WARNING: OVN-Kubernetes namespace exists but no pods found"
    fi
else
    echo "[verify] WARNING: OVN-Kubernetes namespace not found"
    echo "[verify] OVN may need to be installed separately"
fi
echo ""

# Check MPLS modules (requires node access)
echo "[verify] Checking MPLS modules..."
echo "[verify] Note: This requires SSH access to nodes"
echo "[verify] To check manually on each node: lsmod | grep mpls"
echo ""

# Summary
echo "[verify] ========================================"
echo "[verify] Cluster Verification Summary"
echo "[verify] ========================================"
echo "[verify] Nodes: $NODES"
echo "[verify] Ready nodes: $((NODES - NOT_READY))"
echo "[verify] Cluster API: ✓ Accessible"
echo "[verify] ========================================"

