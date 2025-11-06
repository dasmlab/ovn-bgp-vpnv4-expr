# k3s Cluster Installation Guide

This guide provides step-by-step instructions and scripts to set up a k3s cluster with OVN-Kubernetes for VPNv4 driver testing.

## Cluster Topology

- **Control Node:** `k3s-control` (10.20.1.100)
- **Worker Node 1:** `k3s-worker-1` (10.20.1.101)
- **Worker Node 2:** `k3s-worker-2` (10.20.1.102)

## Prerequisites

- Ubuntu 22.04+ on all nodes
- SSH access to all nodes as a regular user (with passwordless sudo)
- SSH keys configured for passwordless access from your dev machine
- User has passwordless sudo on all nodes
- All nodes can reach each other on the network
- Internet access for downloading k3s and OVN images

### Setting Up Passwordless Sudo

On each node, configure passwordless sudo for your user:

```bash
# On each node (10.20.1.100, 10.20.1.101, 10.20.1.102)
echo "$USER ALL=(ALL) NOPASSWD: ALL" | sudo tee /etc/sudoers.d/$USER
```

### Setting Up SSH Keys

From your dev machine, copy SSH keys to all nodes:

```bash
# Replace 'youruser' with your actual username
ssh-copy-id youruser@10.20.1.100
ssh-copy-id youruser@10.20.1.101
ssh-copy-id youruser@10.20.1.102
```

## Quick Start

### Option 1: Automated Installation (Recommended)

Run the master installation script from your local machine:

```bash
# From your local machine (with SSH access to all nodes)
cd scripts/k3s-installation
./install-k3s-cluster.sh
```

This script will:
1. Install k3s on control node
2. Get join token
3. Install k3s on worker nodes
4. Load MPLS modules on all nodes
5. Verify cluster is ready

### Option 2: Manual Installation

Follow the steps below if you prefer manual control.

## Step-by-Step Installation

### Step 1: Prepare All Nodes

On each node (control + workers), run:

```bash
# Update system
sudo apt-get update && sudo apt-get upgrade -y

# Install prerequisites
sudo apt-get install -y curl wget jq

# Set hostnames (run on respective nodes)
# On control node:
sudo hostnamectl set-hostname k3s-control

# On worker-1:
sudo hostnamectl set-hostname k3s-worker-1

# On worker-2:
sudo hostnamectl set-hostname k3s-worker-2

# Add to /etc/hosts on all nodes
cat <<EOF | sudo tee -a /etc/hosts
10.20.1.100 k3s-control
10.20.1.101 k3s-worker-1
10.20.1.102 k3s-worker-2
EOF
```

### Step 2: Install k3s on Control Node

SSH to the control node (10.20.1.100) and run:

```bash
# Run the control node installation script
curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC="--disable traefik --disable servicelb" sh -

# Wait for k3s to be ready
sudo k3s kubectl get nodes

# Get the join token
sudo cat /var/lib/rancher/k3s/server/node-token
```

**Save the join token** - you'll need it for the worker nodes.

### Step 3: Install k3s on Worker Nodes

SSH to each worker node and run:

```bash
# Replace <TOKEN> with the token from control node
# Replace <CONTROL_IP> with 10.20.1.100

curl -sfL https://get.k3s.io | K3S_URL=https://10.20.1.100:6443 K3S_TOKEN=<TOKEN> sh -
```

Or use the provided script:

```bash
# On worker-1 (10.20.1.101)
./install-k3s-worker.sh <TOKEN> 10.20.1.100

# On worker-2 (10.20.1.102)
./install-k3s-worker.sh <TOKEN> 10.20.1.100
```

### Step 4: Verify Cluster

From the control node:

```bash
# Get kubeconfig
sudo cat /etc/rancher/k3s/k3s.yaml

# Copy kubeconfig to your local machine
# Update server address to 10.20.1.100:6443
# Save as ~/.kube/config

# Verify nodes
kubectl get nodes

# Should show:
# NAME            STATUS   ROLES                  AGE   VERSION
# k3s-control     Ready    control-plane,master   1m    v1.28.x
# k3s-worker-1    Ready    <none>                 30s   v1.28.x
# k3s-worker-2    Ready    <none>                 30s   v1.28.x
```

### Step 5: Load MPLS Kernel Modules

On **all nodes** (control + workers), run:

```bash
# Load modules immediately
sudo modprobe mpls_router mpls_iptunnel

# Make persistent
cat <<EOF | sudo tee /etc/modules-load.d/mpls.conf
mpls_router
mpls_iptunnel
EOF

# Verify
lsmod | grep mpls
```

Or use the provided script:

```bash
./load-mpls-modules.sh
```

### Step 6: Install OVN-Kubernetes

OVN-Kubernetes should be installed as part of k3s if using the OVN CNI. Verify:

```bash
# Check OVN pods
kubectl get pods -n ovn-kubernetes

# Check OVN NB DB
kubectl get svc -n ovn-kubernetes | grep ovnkube-db
```

If OVN is not installed, you may need to install it separately. See [OVN-Kubernetes Installation](https://github.com/ovn-org/ovn-kubernetes).

## Verification Checklist

- [ ] All nodes show `Ready` status
- [ ] MPLS modules loaded on all nodes (`lsmod | grep mpls`)
- [ ] OVN-Kubernetes pods running
- [ ] OVN NB DB accessible (port 6641)
- [ ] Can create test pods
- [ ] Network connectivity between nodes

## Next Steps

Once the cluster is ready, proceed with VPNv4 driver deployment:

1. Follow [k3s-deployment.md](../../docs/k3s-deployment.md)
2. Deploy the VPNv4 agent
3. Configure FortiGate peers
4. Test route advertisement

## Troubleshooting

### Nodes not joining

```bash
# Check firewall on control node
sudo ufw status
# Allow port 6443
sudo ufw allow 6443/tcp

# Check k3s service
sudo systemctl status k3s
sudo journalctl -u k3s -f
```

### MPLS modules not loading

```bash
# Check kernel version (must be 5.15+)
uname -r

# Check if modules exist
find /lib/modules/$(uname -r) -name "mpls*.ko"

# Check dmesg
dmesg | grep -i mpls
```

### OVN not working

```bash
# Check OVN pods
kubectl get pods -n ovn-kubernetes

# Check logs
kubectl logs -n ovn-kubernetes -l app=ovnkube-node

# Verify OVN NB DB
kubectl port-forward -n ovn-kubernetes svc/ovnkube-db-nb 6641:6641
# In another terminal:
ovn-nbctl --db=tcp:127.0.0.1:6641 show
```

## Scripts Reference

- `install-k3s-control.sh` - Install k3s on control node
- `install-k3s-worker.sh` - Install k3s on worker node
- `load-mpls-modules.sh` - Load MPLS modules on a node
- `verify-cluster.sh` - Verify cluster is ready
- `install-k3s-cluster.sh` - Master script (automates everything)

