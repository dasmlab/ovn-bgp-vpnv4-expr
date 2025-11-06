#!/usr/bin/env bash
# Load MPLS kernel modules on a node
# Usage: ./load-mpls-modules.sh
# Note: This script should be run via SSH as a sudo user

set -euo pipefail

# When piped via SSH, BASH_SOURCE[0] may be unbound - that's OK, we don't use it

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
    cat <<EOF | sudo tee "$MODULES_FILE"
mpls_router
mpls_iptunnel
EOF
    echo "[mpls-modules] ✓ Modules will load on boot"
else
    echo "[mpls-modules] ✓ Modules already configured for boot"
fi

echo "[mpls-modules] MPLS modules loaded successfully!"
lsmod | grep mpls

