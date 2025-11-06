#!/usr/bin/env bash
# Install k3s on worker node
# Usage: ./install-k3s-worker.sh <TOKEN> <CONTROL_IP>
# Example: ./install-k3s-worker.sh K10abc...xyz 10.20.1.100

set -euo pipefail

if [ $# -lt 2 ]; then
    echo "Usage: $0 <TOKEN> <CONTROL_IP>"
    echo "Example: $0 K10abc...xyz 10.20.1.100"
    exit 1
fi

TOKEN=$1
CONTROL_IP=$2

echo "[k3s-worker] Installing k3s worker node..."
echo "[k3s-worker] Control node: ${CONTROL_IP}"

# Check if already installed
if command -v k3s >/dev/null 2>&1; then
    echo "[k3s-worker] k3s is already installed"
    sudo k3s kubectl get nodes 2>/dev/null || echo "[k3s-worker] Note: kubectl not available on worker nodes"
    exit 0
fi

# Verify connectivity to control node
echo "[k3s-worker] Verifying connectivity to control node..."
if ! ping -c 1 -W 2 "${CONTROL_IP}" >/dev/null 2>&1; then
    echo "[k3s-worker] ERROR: Cannot reach control node at ${CONTROL_IP}"
    exit 1
fi

# Install k3s worker
echo "[k3s-worker] Downloading and installing k3s worker..."
curl -sfL https://get.k3s.io | K3S_URL="https://${CONTROL_IP}:6443" K3S_TOKEN="${TOKEN}" sh -

# Wait for k3s to be ready
echo "[k3s-worker] Waiting for k3s agent to start..."
sleep 5

# Verify installation
if systemctl is-active --quiet k3s-agent; then
    echo "[k3s-worker] k3s worker installed successfully!"
    echo "[k3s-worker] Agent status:"
    sudo systemctl status k3s-agent --no-pager -l
else
    echo "[k3s-worker] ERROR: k3s agent did not start"
    sudo systemctl status k3s-agent --no-pager -l
    exit 1
fi

