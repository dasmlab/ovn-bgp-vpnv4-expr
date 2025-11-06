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
KERNEL_VERSION=$(uname -r)
echo "[mpls-modules] Checking for MPLS modules in kernel ${KERNEL_VERSION}..."

MPLS_ROUTER_MODULE=$(sudo find /lib/modules/${KERNEL_VERSION} -name "mpls_router.ko*" 2>/dev/null | head -1)
MPLS_IPTUNNEL_MODULE=$(sudo find /lib/modules/${KERNEL_VERSION} -name "mpls_iptunnel.ko*" 2>/dev/null | head -1)

if [ -z "$MPLS_ROUTER_MODULE" ]; then
    echo "[mpls-modules] WARNING: mpls_router module not found in /lib/modules/${KERNEL_VERSION}/"
    echo "[mpls-modules] This may mean:"
    echo "  - Kernel was built without MPLS support"
    echo "  - MPLS modules are built-in (not loadable)"
    echo "  - Different kernel version is running"
    echo ""
    echo "[mpls-modules] Checking if MPLS is built into kernel..."
    if grep -q "CONFIG_MPLS=y" /boot/config-${KERNEL_VERSION} 2>/dev/null || \
       grep -q "CONFIG_MPLS_ROUTING=y" /boot/config-${KERNEL_VERSION} 2>/dev/null; then
        echo "[mpls-modules] MPLS appears to be built into kernel (not a module)"
        echo "[mpls-modules] Attempting to load anyway (may already be available)..."
    else
        echo "[mpls-modules] ERROR: MPLS support not found in kernel configuration"
        echo "[mpls-modules] You may need to:"
        echo "  1. Install a kernel with MPLS support"
        echo "  2. Or build a custom kernel with CONFIG_MPLS and CONFIG_MPLS_ROUTING enabled"
        exit 1
    fi
else
    echo "[mpls-modules] Found mpls_router module: ${MPLS_ROUTER_MODULE}"
fi

if [ -z "$MPLS_IPTUNNEL_MODULE" ]; then
    echo "[mpls-modules] WARNING: mpls_iptunnel module not found"
    echo "[mpls-modules] Checking if it's built into kernel..."
    if grep -q "CONFIG_MPLS_IPTUNNEL=y" /boot/config-${KERNEL_VERSION} 2>/dev/null; then
        echo "[mpls-modules] mpls_iptunnel appears to be built into kernel"
    else
        echo "[mpls-modules] ERROR: mpls_iptunnel not found"
        exit 1
    fi
else
    echo "[mpls-modules] Found mpls_iptunnel module: ${MPLS_IPTUNNEL_MODULE}"
fi

# Load modules (requires root)
echo "[mpls-modules] Loading mpls_router..."
MPLS_ROUTER_ERROR=$(sudo modprobe mpls_router 2>&1) || {
    MPLS_ROUTER_EXIT=$?
    echo "[mpls-modules] ERROR: Failed to load mpls_router (exit code: ${MPLS_ROUTER_EXIT})"
    echo "[mpls-modules] Error output: ${MPLS_ROUTER_ERROR}"
    
    # Check if module exists
    if ! sudo find /lib/modules/$(uname -r) -name "mpls_router.ko*" >/dev/null 2>&1; then
        echo "[mpls-modules] Module file not found - kernel may not have MPLS support"
        echo "[mpls-modules] Check kernel config: grep MPLS /boot/config-$(uname -r) 2>/dev/null || echo 'Config not available'"
    fi
    
    # Check dmesg for more details
    echo "[mpls-modules] Recent kernel messages:"
    sudo dmesg | tail -10 | grep -i mpls || echo "  (no MPLS-related messages)"
    exit 1
}

echo "[mpls-modules] Loading mpls_iptunnel..."
MPLS_IPTUNNEL_ERROR=$(sudo modprobe mpls_iptunnel 2>&1) || {
    MPLS_IPTUNNEL_EXIT=$?
    echo "[mpls-modules] ERROR: Failed to load mpls_iptunnel (exit code: ${MPLS_IPTUNNEL_EXIT})"
    echo "[mpls-modules] Error output: ${MPLS_IPTUNNEL_ERROR}"
    
    # Check dmesg for more details
    echo "[mpls-modules] Recent kernel messages:"
    sudo dmesg | tail -10 | grep -i mpls || echo "  (no MPLS-related messages)"
    exit 1
}

# Give modules a moment to register
sleep 1

# Verify modules are loaded
if lsmod | grep -q "^mpls_router"; then
    echo "[mpls-modules] ✓ mpls_router loaded"
else
    echo "[mpls-modules] ERROR: mpls_router modprobe succeeded but module not in lsmod"
    echo "[mpls-modules] Checking module status..."
    lsmod | grep mpls || echo "  (no MPLS modules found)"
    sudo dmesg | tail -20 | grep -i mpls || echo "  (no MPLS-related messages)"
    exit 1
fi

if lsmod | grep -q "^mpls_iptunnel"; then
    echo "[mpls-modules] ✓ mpls_iptunnel loaded"
else
    echo "[mpls-modules] ERROR: mpls_iptunnel modprobe succeeded but module not in lsmod"
    echo "[mpls-modules] Checking module status..."
    lsmod | grep mpls || echo "  (no MPLS modules found)"
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

