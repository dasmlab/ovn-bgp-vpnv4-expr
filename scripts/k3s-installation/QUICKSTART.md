# k3s Cluster Quick Start

Quick reference for setting up the 3-node k3s cluster.

## Prerequisites Check

```bash
# Verify SSH access to all nodes (replace 'youruser' with your username)
ssh youruser@10.20.1.100 "echo 'Control node OK'"
ssh youruser@10.20.1.101 "echo 'Worker 1 OK'"
ssh youruser@10.20.1.102 "echo 'Worker 2 OK'"
```

If SSH requires password, set up SSH keys:
```bash
ssh-copy-id youruser@10.20.1.100
ssh-copy-id youruser@10.20.1.101
ssh-copy-id youruser@10.20.1.102
```

Verify passwordless sudo on all nodes:
```bash
ssh youruser@10.20.1.100 "sudo -n echo 'sudo OK'"
ssh youruser@10.20.1.101 "sudo -n echo 'sudo OK'"
ssh youruser@10.20.1.102 "sudo -n echo 'sudo OK'"
```

If sudo requires password, configure passwordless sudo on each node:
```bash
# On each node
echo "$USER ALL=(ALL) NOPASSWD: ALL" | sudo tee /etc/sudoers.d/$USER
```

## Automated Installation

```bash
cd scripts/k3s-installation

# Step 1: Prepare all nodes (uses current user by default)
./prepare-nodes.sh

# Step 2: Install k3s cluster
./install-k3s-cluster.sh

# Or specify a different user:
SSH_USER=ubuntu ./prepare-nodes.sh
SSH_USER=ubuntu ./install-k3s-cluster.sh
```

## Manual Installation

### 1. Control Node (10.20.1.100)

```bash
ssh youruser@10.20.1.100
# Copy script to node or run via SSH
bash <(curl -s https://raw.githubusercontent.com/your-repo/scripts/k3s-installation/install-k3s-control.sh)
# Or if script is already on node:
./install-k3s-control.sh
# Save the join token that's displayed
```

### 2. Worker Nodes

```bash
# On worker-1 (10.20.1.101)
ssh youruser@10.20.1.101
./install-k3s-worker.sh <TOKEN> 10.20.1.100

# On worker-2 (10.20.1.102)
ssh youruser@10.20.1.102
./install-k3s-worker.sh <TOKEN> 10.20.1.100
```

### 3. Load MPLS Modules (All Nodes)

```bash
# On each node
./load-mpls-modules.sh
```

### 4. Get Kubeconfig

```bash
# From control node
sudo cat /etc/rancher/k3s/k3s.yaml

# Copy to local machine, update server address:
# server: https://10.20.1.100:6443
# Save as ~/.kube/config
```

## Verify

```bash
kubectl get nodes
# Should show 3 nodes, all Ready
```

## Next Steps

Follow [k3s-deployment.md](../../docs/k3s-deployment.md) to deploy the VPNv4 driver.

