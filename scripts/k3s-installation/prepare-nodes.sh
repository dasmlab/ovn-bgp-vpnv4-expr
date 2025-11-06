#!/usr/bin/env bash
# Prepare all nodes (hostname, hosts file, prerequisites)
# Usage: ./prepare-nodes.sh [--user USER]
#
# Environment variables:
# - SSH_USER: SSH user (default: root)

set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)

CONTROL_NODE="10.20.1.100"
CONTROL_HOST="k3s-control"
WORKER1_NODE="10.20.1.101"
WORKER1_HOST="k3s-worker-1"
WORKER2_NODE="10.20.1.102"
WORKER2_HOST="k3s-worker-2"

SSH_USER="${SSH_USER:-root}"
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
apt-get update && apt-get upgrade -y

# Install prerequisites
echo "[${hostname}] Installing prerequisites..."
apt-get install -y curl wget jq

# Set hostname
echo "[${hostname}] Setting hostname..."
hostnamectl set-hostname ${hostname}

# Add to /etc/hosts
echo "[${hostname}] Updating /etc/hosts..."
if ! grep -q "k3s-control" /etc/hosts; then
    cat <<HOSTS_EOF >> /etc/hosts
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

