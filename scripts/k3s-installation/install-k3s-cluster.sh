#!/usr/bin/env bash
# Master script to install k3s cluster with 1 control + 2 workers
# Usage: ./install-k3s-cluster.sh [--skip-mpls] [--skip-verify]
#
# Prerequisites:
# - SSH access to all nodes with sudo privileges
# - Passwordless SSH or SSH keys configured
# - Control node: 10.20.1.100 (k3s-control)
# - Worker 1: 10.20.1.101 (k3s-worker-1)
# - Worker 2: 10.20.1.102 (k3s-worker-2)

set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)

# Node configuration
CONTROL_NODE="10.20.1.100"
CONTROL_HOST="k3s-control"
WORKER1_NODE="10.20.1.101"
WORKER1_HOST="k3s-worker-1"
WORKER2_NODE="10.20.1.102"
WORKER2_HOST="k3s-worker-2"

# Options
SKIP_MPLS=false
SKIP_VERIFY=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-mpls)
            SKIP_MPLS=true
            shift
            ;;
        --skip-verify)
            SKIP_VERIFY=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--skip-mpls] [--skip-verify]"
            exit 1
            ;;
    esac
done

echo "=========================================="
echo "k3s Cluster Installation"
echo "=========================================="
echo "Control:  ${CONTROL_HOST} (${CONTROL_NODE})"
echo "Worker 1: ${WORKER1_HOST} (${WORKER1_NODE})"
echo "Worker 2: ${WORKER2_HOST} (${WORKER2_NODE})"
echo "=========================================="
echo ""

# Check SSH access
echo "[install] Checking SSH access to nodes..."
for node in "${CONTROL_NODE}" "${WORKER1_NODE}" "${WORKER2_NODE}"; do
    if ! ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no "root@${node}" "echo 'SSH OK'" >/dev/null 2>&1; then
        echo "[install] ERROR: Cannot SSH to ${node}"
        echo "[install] Please ensure:"
        echo "  - SSH keys are configured"
        echo "  - User has sudo privileges"
        echo "  - Nodes are reachable"
        exit 1
    fi
    echo "[install] ✓ SSH access to ${node}"
done
echo ""

# Step 1: Install on control node
echo "[install] Step 1/5: Installing k3s on control node..."
ssh "root@${CONTROL_NODE}" "bash -s" < "${SCRIPT_DIR}/install-k3s-control.sh"

# Get join token
echo "[install] Step 2/5: Getting join token..."
JOIN_TOKEN=$(ssh "root@${CONTROL_NODE}" "sudo cat /var/lib/rancher/k3s/server/node-token")
echo "[install] Join token: ${JOIN_TOKEN:0:20}..."
echo ""

# Step 3: Install on worker nodes
echo "[install] Step 3/5: Installing k3s on worker nodes..."
echo "[install] Installing on ${WORKER1_HOST}..."
ssh "root@${WORKER1_NODE}" "bash -s" < "${SCRIPT_DIR}/install-k3s-worker.sh" -- "${JOIN_TOKEN}" "${CONTROL_NODE}"

echo "[install] Installing on ${WORKER2_HOST}..."
ssh "root@${WORKER2_NODE}" "bash -s" < "${SCRIPT_DIR}/install-k3s-worker.sh" -- "${JOIN_TOKEN}" "${CONTROL_NODE}"

# Wait for workers to join
echo "[install] Waiting for workers to join cluster..."
sleep 10

# Step 4: Load MPLS modules
if [ "$SKIP_MPLS" = false ]; then
    echo "[install] Step 4/5: Loading MPLS modules on all nodes..."
    for node in "${CONTROL_NODE}" "${WORKER1_NODE}" "${WORKER2_NODE}"; do
        echo "[install] Loading MPLS modules on ${node}..."
        ssh "root@${node}" "bash -s" < "${SCRIPT_DIR}/load-mpls-modules.sh" || {
            echo "[install] WARNING: Failed to load MPLS modules on ${node}"
        }
    done
else
    echo "[install] Step 4/5: Skipping MPLS modules (--skip-mpls)"
fi
echo ""

# Step 5: Verify cluster
if [ "$SKIP_VERIFY" = false ]; then
    echo "[install] Step 5/5: Verifying cluster..."
    
    # Get kubeconfig
    echo "[install] Fetching kubeconfig..."
    ssh "root@${CONTROL_NODE}" "sudo cat /etc/rancher/k3s/k3s.yaml" | \
        sed "s/127.0.0.1/${CONTROL_NODE}/g" > /tmp/k3s-kubeconfig.yaml
    
    # Verify
    KUBECONFIG=/tmp/k3s-kubeconfig.yaml "${SCRIPT_DIR}/verify-cluster.sh" /tmp/k3s-kubeconfig.yaml
    
    echo ""
    echo "[install] Kubeconfig saved to: /tmp/k3s-kubeconfig.yaml"
    echo "[install] To use: export KUBECONFIG=/tmp/k3s-kubeconfig.yaml"
else
    echo "[install] Step 5/5: Skipping verification (--skip-verify)"
fi

echo ""
echo "=========================================="
echo "Installation Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Copy kubeconfig:"
echo "   scp root@${CONTROL_NODE}:/etc/rancher/k3s/k3s.yaml ~/.kube/config"
echo "   # Update server address to: https://${CONTROL_NODE}:6443"
echo ""
echo "2. Verify cluster:"
echo "   kubectl get nodes"
echo ""
echo "3. Deploy VPNv4 driver:"
echo "   Follow docs/k3s-deployment.md"
echo ""

