#!/usr/bin/env bash
# Install k3s on control node
# Usage: ./install-k3s-control.sh
# Note: This script should be run via SSH as a sudo user

set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)

echo "[k3s-control] Installing k3s on control node..."

# Check if already installed
if command -v k3s >/dev/null 2>&1 || sudo command -v k3s >/dev/null 2>&1; then
    echo "[k3s-control] k3s is already installed"
    sudo k3s kubectl get nodes
    exit 0
fi

# Install k3s (requires root/sudo)
echo "[k3s-control] Downloading and installing k3s..."
curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC="--disable traefik --disable servicelb" sudo sh -

# Wait for k3s to be ready
echo "[k3s-control] Waiting for k3s to be ready..."
timeout=60
elapsed=0
while ! sudo k3s kubectl get nodes >/dev/null 2>&1; do
    if [ $elapsed -ge $timeout ]; then
        echo "[k3s-control] ERROR: k3s did not start within ${timeout}s"
        exit 1
    fi
    sleep 2
    elapsed=$((elapsed + 2))
done

# Get node token
TOKEN=$(sudo cat /var/lib/rancher/k3s/server/node-token)
echo "[k3s-control] k3s installed successfully!"
echo "[k3s-control] Node token: ${TOKEN}"
echo ""
echo "[k3s-control] Save this token for worker node installation"
echo "[k3s-control] To get it again later: sudo cat /var/lib/rancher/k3s/server/node-token"

# Show nodes
echo ""
echo "[k3s-control] Cluster status:"
sudo k3s kubectl get nodes

# Show kubeconfig location
echo ""
echo "[k3s-control] Kubeconfig location: /etc/rancher/k3s/k3s.yaml"
echo "[k3s-control] To use from local machine:"
echo "  sudo cat /etc/rancher/k3s/k3s.yaml"
echo "  # Update server address to: https://10.20.1.100:6443"
echo "  # Save as ~/.kube/config"

