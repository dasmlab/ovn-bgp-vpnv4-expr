#!/usr/bin/env bash
# Master script to install k3s cluster with 1 control + 2 workers
# Usage: ./install-k3s-cluster.sh [--skip-mpls] [--skip-verify] [--user USER]
#
# Prerequisites:
# - SSH access to all nodes as a sudo user
# - SSH keys configured for passwordless access
# - User has passwordless sudo privileges
# - Control node: 10.20.1.100 (k3s-control)
# - Worker 1: 10.20.1.101 (k3s-worker-1)
# - Worker 2: 10.20.1.102 (k3s-worker-2)
#
# Environment variables:
# - SSH_USER: SSH user (default: current user, or set via --user)
# - SSH_OPTS: Additional SSH options

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
SSH_USER="${SSH_USER:-${USER}}"
SSH_OPTS="${SSH_OPTS:--o StrictHostKeyChecking=no -o ConnectTimeout=10}"

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
        --user)
            SSH_USER="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--skip-mpls] [--skip-verify] [--user USER]"
            echo ""
            echo "Default SSH user: ${USER} (current user)"
            echo "Ensure the user has passwordless sudo on all nodes"
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
echo "[install] Using SSH user: ${SSH_USER}"
for node in "${CONTROL_NODE}" "${WORKER1_NODE}" "${WORKER2_NODE}"; do
    if ! ssh ${SSH_OPTS} "${SSH_USER}@${node}" "echo 'SSH OK'" >/dev/null 2>&1; then
        echo "[install] ERROR: Cannot SSH to ${SSH_USER}@${node}"
        echo "[install] Please ensure:"
        echo "  - SSH keys are configured for ${SSH_USER}"
        echo "  - User has passwordless sudo privileges"
        echo "  - Nodes are reachable"
        echo ""
        echo "[install] Try: ssh ${SSH_USER}@${node} 'echo test'"
        exit 1
    fi
    
    # Verify sudo access
    if ! ssh ${SSH_OPTS} "${SSH_USER}@${node}" "sudo -n echo 'sudo OK'" >/dev/null 2>&1; then
        echo "[install] ERROR: User ${SSH_USER}@${node} does not have passwordless sudo"
        echo "[install] Please configure passwordless sudo:"
        echo "  echo '${SSH_USER} ALL=(ALL) NOPASSWD: ALL' | sudo tee /etc/sudoers.d/${SSH_USER}"
        exit 1
    fi
    
    echo "[install] ✓ SSH and sudo access to ${SSH_USER}@${node}"
done
echo ""

# Verify DNS resolution on all nodes
echo "[install] Verifying DNS resolution on all nodes..."
for node in "${CONTROL_NODE}" "${WORKER1_NODE}" "${WORKER2_NODE}"; do
    echo "[install] Checking DNS on ${node}..."
    # Try getent hosts first (uses system resolver, no extra packages needed)
    if ssh ${SSH_OPTS} "${SSH_USER}@${node}" "getent hosts www.google.com >/dev/null 2>&1"; then
        echo "[install] ✓ DNS resolution working on ${node}"
    else
        # Fallback to ping (usually available, but might be blocked by firewall)
        if ssh ${SSH_OPTS} "${SSH_USER}@${node}" "ping -c 1 -W 2 www.google.com >/dev/null 2>&1"; then
            echo "[install] ✓ DNS resolution working on ${node} (via ping)"
        else
            echo "[install] ERROR: DNS resolution failed on ${node}"
            echo "[install] Please check /etc/resolv.conf and ensure DNS servers are configured"
            echo "[install] Test manually: ssh ${SSH_USER}@${node} 'getent hosts www.google.com'"
            exit 1
        fi
    fi
done
echo ""

# Step 1: Install on control node
echo "[install] Step 1/5: Installing k3s on control node..."
# Use bash with set -u disabled for BASH_SOURCE to avoid unbound variable error when piping
# Capture both stdout and stderr, and ensure errors are visible
if ! ssh ${SSH_OPTS} "${SSH_USER}@${CONTROL_NODE}" "bash" <<'EOF' 2>&1; then
set -eo pipefail
# Install k3s on control node
echo "[k3s-control] Installing k3s on control node..."

# Check if already installed
if command -v k3s >/dev/null 2>&1 || sudo command -v k3s >/dev/null 2>&1; then
    echo "[k3s-control] k3s is already installed"
    sudo k3s kubectl get nodes
    exit 0
fi

# Install k3s (requires root/sudo)
echo "[k3s-control] Downloading and installing k3s..."
echo "[k3s-control] Running: curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC=\"--disable traefik --disable servicelb\" sudo sh -"
if ! curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC="--disable traefik --disable servicelb" sudo sh -; then
    echo "[k3s-control] ERROR: k3s installation failed"
    echo "[k3s-control] Checking for error logs..."
    sudo journalctl -u k3s --no-pager -n 20 2>/dev/null || true
    exit 1
fi

# Wait for k3s to be ready
echo "[k3s-control] Waiting for k3s to be ready..."
timeout=60
elapsed=0
while ! sudo k3s kubectl get nodes >/dev/null 2>&1; do
    if [ $elapsed -ge $timeout ]; then
        echo "[k3s-control] ERROR: k3s did not start within ${timeout}s"
        echo "[k3s-control] Checking k3s service status..."
        sudo systemctl status k3s --no-pager -l || true
        echo "[k3s-control] Recent logs:"
        sudo journalctl -u k3s --no-pager -n 30 2>/dev/null || true
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
EOF
    echo "[install] ERROR: Failed to install k3s on control node"
    echo "[install] Check the output above for details"
    exit 1
fi

# Get join token
echo "[install] Step 2/5: Getting join token..."
JOIN_TOKEN=$(ssh ${SSH_OPTS} "${SSH_USER}@${CONTROL_NODE}" "sudo cat /var/lib/rancher/k3s/server/node-token")
echo "[install] Join token: ${JOIN_TOKEN:0:20}..."
echo ""

# Step 3: Install on worker nodes
echo "[install] Step 3/5: Installing k3s on worker nodes..."
echo "[install] Installing on ${WORKER1_HOST}..."
if ! ssh ${SSH_OPTS} "${SSH_USER}@${WORKER1_NODE}" "bash" <<EOF 2>&1; then
set -eo pipefail
TOKEN="${JOIN_TOKEN}"
CONTROL_IP="${CONTROL_NODE}"

echo "[k3s-worker] Installing k3s worker node..."
echo "[k3s-worker] Control node: \${CONTROL_IP}"

# Check if already installed
if command -v k3s >/dev/null 2>&1 || sudo command -v k3s >/dev/null 2>&1; then
    echo "[k3s-worker] k3s is already installed"
    sudo k3s kubectl get nodes 2>/dev/null || echo "[k3s-worker] Note: kubectl not available on worker nodes"
    exit 0
fi

# Verify connectivity to control node
echo "[k3s-worker] Verifying connectivity to control node..."
if ! ping -c 1 -W 2 "\${CONTROL_IP}" >/dev/null 2>&1; then
    echo "[k3s-worker] ERROR: Cannot reach control node at \${CONTROL_IP}"
    exit 1
fi

# Install k3s worker (requires root/sudo)
echo "[k3s-worker] Downloading and installing k3s worker..."
if ! curl -sfL https://get.k3s.io | K3S_URL="https://\${CONTROL_IP}:6443" K3S_TOKEN="\${TOKEN}" sudo sh -; then
    echo "[k3s-worker] ERROR: k3s worker installation failed"
    sudo journalctl -u k3s-agent --no-pager -n 20 2>/dev/null || true
    exit 1
fi

# Wait for k3s agent to start (with retries for slower systems)
echo "[k3s-worker] Waiting for k3s agent to start..."
timeout=120
elapsed=0
while ! systemctl is-active --quiet k3s-agent; do
    if [ $elapsed -ge $timeout ]; then
        echo "[k3s-worker] ERROR: k3s agent did not start within ${timeout}s"
        echo "[k3s-worker] Service status:"
        sudo systemctl status k3s-agent --no-pager -l || true
        echo "[k3s-worker] Recent logs:"
        sudo journalctl -u k3s-agent --no-pager -n 30 2>/dev/null || true
        exit 1
    fi
    sleep 3
    elapsed=$((elapsed + 3))
    if [ $((elapsed % 15)) -eq 0 ]; then
        echo "[k3s-worker] Still waiting for agent to start... (${elapsed}s elapsed)"
    fi
done

# Give it a bit more time to fully initialize
echo "[k3s-worker] Agent is active, waiting for full initialization..."
sleep 5

# Verify installation
echo "[k3s-worker] k3s worker installed successfully!"
echo "[k3s-worker] Agent status:"
sudo systemctl status k3s-agent --no-pager -l
EOF
    echo "[install] ERROR: Failed to install k3s on ${WORKER1_HOST}"
    exit 1
fi

echo "[install] Installing on ${WORKER2_HOST}..."
if ! ssh ${SSH_OPTS} "${SSH_USER}@${WORKER2_NODE}" "bash" <<EOF 2>&1; then
set -eo pipefail
TOKEN="${JOIN_TOKEN}"
CONTROL_IP="${CONTROL_NODE}"

echo "[k3s-worker] Installing k3s worker node..."
echo "[k3s-worker] Control node: \${CONTROL_IP}"

# Check if already installed
if command -v k3s >/dev/null 2>&1 || sudo command -v k3s >/dev/null 2>&1; then
    echo "[k3s-worker] k3s is already installed"
    sudo k3s kubectl get nodes 2>/dev/null || echo "[k3s-worker] Note: kubectl not available on worker nodes"
    exit 0
fi

# Verify connectivity to control node
echo "[k3s-worker] Verifying connectivity to control node..."
if ! ping -c 1 -W 2 "\${CONTROL_IP}" >/dev/null 2>&1; then
    echo "[k3s-worker] ERROR: Cannot reach control node at \${CONTROL_IP}"
    exit 1
fi

# Install k3s worker (requires root/sudo)
echo "[k3s-worker] Downloading and installing k3s worker..."
if ! curl -sfL https://get.k3s.io | K3S_URL="https://\${CONTROL_IP}:6443" K3S_TOKEN="\${TOKEN}" sudo sh -; then
    echo "[k3s-worker] ERROR: k3s worker installation failed"
    sudo journalctl -u k3s-agent --no-pager -n 20 2>/dev/null || true
    exit 1
fi

# Wait for k3s agent to start (with retries for slower systems)
echo "[k3s-worker] Waiting for k3s agent to start..."
timeout=120
elapsed=0
while ! systemctl is-active --quiet k3s-agent; do
    if [ $elapsed -ge $timeout ]; then
        echo "[k3s-worker] ERROR: k3s agent did not start within ${timeout}s"
        echo "[k3s-worker] Service status:"
        sudo systemctl status k3s-agent --no-pager -l || true
        echo "[k3s-worker] Recent logs:"
        sudo journalctl -u k3s-agent --no-pager -n 30 2>/dev/null || true
        exit 1
    fi
    sleep 3
    elapsed=$((elapsed + 3))
    if [ $((elapsed % 15)) -eq 0 ]; then
        echo "[k3s-worker] Still waiting for agent to start... (${elapsed}s elapsed)"
    fi
done

# Give it a bit more time to fully initialize
echo "[k3s-worker] Agent is active, waiting for full initialization..."
sleep 5

# Verify installation
echo "[k3s-worker] k3s worker installed successfully!"
echo "[k3s-worker] Agent status:"
sudo systemctl status k3s-agent --no-pager -l
EOF
    echo "[install] ERROR: Failed to install k3s on ${WORKER2_HOST}"
    exit 1
fi

# Wait for workers to join cluster and appear in node list
echo "[install] Waiting for workers to join cluster..."
timeout=120
elapsed=0
EXPECTED_NODES=3  # 1 control + 2 workers

while true; do
    NODE_COUNT=$(ssh ${SSH_OPTS} "${SSH_USER}@${CONTROL_NODE}" "sudo k3s kubectl get nodes --no-headers 2>/dev/null | wc -l" || echo "0")
    
    if [ "$NODE_COUNT" -ge "$EXPECTED_NODES" ]; then
        echo "[install] ✓ All ${EXPECTED_NODES} nodes are in the cluster"
        break
    fi
    
    if [ $elapsed -ge $timeout ]; then
        echo "[install] WARNING: Not all nodes joined within ${timeout}s"
        echo "[install] Current node count: ${NODE_COUNT} (expected: ${EXPECTED_NODES})"
        echo "[install] Node status:"
        ssh ${SSH_OPTS} "${SSH_USER}@${CONTROL_NODE}" "sudo k3s kubectl get nodes" || true
        # Don't exit - continue to show status
        break
    fi
    
    sleep 5
    elapsed=$((elapsed + 5))
    if [ $((elapsed % 15)) -eq 0 ]; then
        echo "[install] Waiting for workers to join... (${elapsed}s elapsed, ${NODE_COUNT}/${EXPECTED_NODES} nodes)"
    fi
done

# Step 4: Load MPLS modules
if [ "$SKIP_MPLS" = false ]; then
    echo "[install] Step 4/5: Loading MPLS modules on all nodes..."
    for node in "${CONTROL_NODE}" "${WORKER1_NODE}" "${WORKER2_NODE}"; do
        echo "[install] Loading MPLS modules on ${node}..."
        ssh ${SSH_OPTS} "${SSH_USER}@${node}" "bash" <<'EOF' || {
set -eo pipefail
echo "[mpls-modules] Loading MPLS kernel modules..."

# Check kernel version
KERNEL_VERSION=$(uname -r | cut -d. -f1,2)
REQUIRED_VERSION="5.15"

if [ "$(printf '%s\n' "$REQUIRED_VERSION" "$KERNEL_VERSION" | sort -V | head -n1)" != "$REQUIRED_VERSION" ]; then
    echo "[mpls-modules] WARNING: Kernel version ${KERNEL_VERSION} may not support MPLS modules"
    echo "[mpls-modules] Recommended: kernel 5.15+"
fi

# Check if modules exist (requires root to read /lib/modules)
if ! sudo find /lib/modules/$(uname -r) -name "mpls_router.ko" >/dev/null 2>&1; then
    echo "[mpls-modules] ERROR: mpls_router module not found"
    echo "[mpls-modules] Kernel may not have MPLS support compiled in"
    exit 1
fi

# Load modules (requires root)
echo "[mpls-modules] Loading mpls_router..."
sudo modprobe mpls_router || {
    echo "[mpls-modules] ERROR: Failed to load mpls_router"
    exit 1
}

echo "[mpls-modules] Loading mpls_iptunnel..."
sudo modprobe mpls_iptunnel || {
    echo "[mpls-modules] ERROR: Failed to load mpls_iptunnel"
    exit 1
}

# Verify modules are loaded
if lsmod | grep -q "^mpls_router"; then
    echo "[mpls-modules] ✓ mpls_router loaded"
else
    echo "[mpls-modules] ERROR: mpls_router not loaded"
    exit 1
fi

if lsmod | grep -q "^mpls_iptunnel"; then
    echo "[mpls-modules] ✓ mpls_iptunnel loaded"
else
    echo "[mpls-modules] ERROR: mpls_iptunnel not loaded"
    exit 1
fi

# Make persistent
MODULES_FILE="/etc/modules-load.d/mpls.conf"
if [ ! -f "$MODULES_FILE" ] || ! grep -q "mpls_router" "$MODULES_FILE"; then
    echo "[mpls-modules] Making modules persistent..."
    cat <<MODULES_EOF | sudo tee "$MODULES_FILE"
mpls_router
mpls_iptunnel
MODULES_EOF
    echo "[mpls-modules] ✓ Modules will load on boot"
else
    echo "[mpls-modules] ✓ Modules already configured for boot"
fi

echo "[mpls-modules] MPLS modules loaded successfully!"
lsmod | grep mpls
EOF
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
    ssh ${SSH_OPTS} "${SSH_USER}@${CONTROL_NODE}" "sudo cat /etc/rancher/k3s/k3s.yaml" | \
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
echo "   scp ${SSH_USER}@${CONTROL_NODE}:/etc/rancher/k3s/k3s.yaml ~/.kube/config"
echo "   # Update server address to: https://${CONTROL_NODE}:6443"
echo ""
echo "2. Verify cluster:"
echo "   kubectl get nodes"
echo ""
echo "3. Deploy VPNv4 driver:"
echo "   Follow docs/k3s-deployment.md"
echo ""

