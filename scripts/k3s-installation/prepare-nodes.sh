#!/usr/bin/env bash
# Prepare all nodes (hostname, hosts file, prerequisites)
# Usage: ./prepare-nodes.sh [--user USER]
#
# Environment variables:
# - SSH_USER: SSH user (default: current user)

set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)

CONTROL_NODE="10.20.1.100"
CONTROL_HOST="k3s-control"
WORKER1_NODE="10.20.1.101"
WORKER1_HOST="k3s-worker-1"
WORKER2_NODE="10.20.1.102"
WORKER2_HOST="k3s-worker-2"

SSH_USER="${SSH_USER:-${USER}}"
SSH_OPTS="${SSH_OPTS:--o StrictHostKeyChecking=no -o ConnectTimeout=10}"

while [[ $# -gt 0 ]]; do
    case $1 in
        --user)
            SSH_USER="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--user USER]"
            exit 1
            ;;
    esac
done

echo "[prepare] Preparing all nodes..."
echo "[prepare] Using SSH user: ${SSH_USER}"
echo "[prepare] Ensure user has passwordless sudo on all nodes"
echo ""

# Verify SSH and sudo access
for node_ip in "${CONTROL_NODE}" "${WORKER1_NODE}" "${WORKER2_NODE}"; do
    if ! ssh ${SSH_OPTS} "${SSH_USER}@${node_ip}" "sudo -n echo 'sudo OK'" >/dev/null 2>&1; then
        echo "[prepare] ERROR: User ${SSH_USER}@${node_ip} does not have passwordless sudo"
        echo "[prepare] Please configure passwordless sudo first"
        exit 1
    fi
done
echo ""

# Function to prepare a node
prepare_node() {
    local node_ip=$1
    local hostname=$2
    
    echo "[prepare] Preparing ${hostname} (${node_ip})..."
    
    ssh ${SSH_OPTS} "${SSH_USER}@${node_ip}" bash <<EOF
set -euo pipefail

# Update system
echo "[${hostname}] Updating system..."
sudo apt-get update && sudo apt-get upgrade -y

# Install prerequisites
echo "[${hostname}] Installing prerequisites..."
sudo apt-get install -y curl wget jq

# Set hostname
echo "[${hostname}] Setting hostname..."
sudo hostnamectl set-hostname ${hostname}

# Add to /etc/hosts
echo "[${hostname}] Updating /etc/hosts..."
if ! grep -q "k3s-control" /etc/hosts; then
    cat <<HOSTS_EOF | sudo tee -a /etc/hosts >/dev/null
${CONTROL_NODE} ${CONTROL_HOST}
${WORKER1_NODE} ${WORKER1_HOST}
${WORKER2_NODE} ${WORKER2_HOST}
HOSTS_EOF
fi

# Verify
echo "[${hostname}] Verification:"
echo "  Hostname: \$(hostname)"
echo "  Prerequisites installed: ✓"
EOF
    
    echo "[prepare] ✓ ${hostname} prepared"
    echo ""
}

# Prepare all nodes
prepare_node "${CONTROL_NODE}" "${CONTROL_HOST}"
prepare_node "${WORKER1_NODE}" "${WORKER1_HOST}"
prepare_node "${WORKER2_NODE}" "${WORKER2_HOST}"

echo "[prepare] All nodes prepared!"
echo ""
echo "Next: Run install-k3s-cluster.sh to install k3s"

