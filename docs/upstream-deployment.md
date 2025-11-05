# Upstream Agent Deployment Guide

This guide explains how to deploy the VPNv4 driver using the **upstream `ovn-bgp-agent` service** (recommended for production).

## Overview

The upstream agent integration requires:
1. **Docker image** with upstream agent + VPNv4 driver
2. **Configuration** via oslo.config (INI format)
3. **DaemonSet** deployment in the cluster

## Step 1: Build the Docker Image

The upstream agent image includes:
- `ovn-bgp-agent` package (from PyPI)
- Our VPNv4 driver code (installed as a package)
- Stevedore entry point registration

Build the image:

```bash
make upstream-agent-image UPSTREAM_AGENT_IMAGE=ghcr.io/your-org/ovn-bgp-agent:vpnv4-upstream
```

Push to your registry:

```bash
make upstream-agent-push UPSTREAM_AGENT_IMAGE=ghcr.io/your-org/ovn-bgp-agent:vpnv4-upstream
```

## Step 2: Configure the Agent

The upstream agent uses **oslo.config** with INI format. Edit `deploy/ocp/ovn-bgp-agent-upstream-config.yaml`:

```ini
[DEFAULT]
driver = vpnv4_driver          # Selects our VPNv4 driver
bgp_AS = 65000                 # BGP ASN
bgp_router_id = 10.255.0.2     # Router ID
vpnv4_output_dir = /etc/frr/vpnv4
vpnv4_rd_base = 65000          # RD allocation base
vpnv4_rt_base = 65000          # RT allocation base
vpnv4_peers = 192.0.2.11:65101:fortigate-1,192.0.2.12:65102:fortigate-2
```

**Key settings:**
- `driver = vpnv4_driver` - This tells the upstream agent to load our driver
- `vpnv4_peers` - Format: `"address:asn:description,address2:asn2:description2"`

Apply the ConfigMap:

```bash
oc apply -f deploy/ocp/ovn-bgp-agent-upstream-config.yaml
```

## Step 3: Deploy the DaemonSet

Update `deploy/ocp/ovn-bgp-agent-daemonset-patch.yaml` with your image:

```yaml
image: ghcr.io/your-org/ovn-bgp-agent:vpnv4-upstream
args:
  - --config-file=/etc/ovn-bgp-agent/ovn-bgp-agent.conf
```

Apply the patch:

```bash
oc patch daemonset ovn-bgp-agent -n openshift-ovn-kubernetes \
  --patch-file deploy/ocp/ovn-bgp-agent-daemonset-patch.yaml
```

## Step 4: Verify Deployment

Check pods are running:

```bash
oc get pods -n openshift-ovn-kubernetes -l app=ovn-bgp-agent
```

Check logs to verify driver is loaded:

```bash
oc logs -n openshift-ovn-kubernetes -l app=ovn-bgp-agent | grep -i vpnv4
```

You should see:
- `VPNv4UpstreamDriver initialized`
- `VPNv4UpstreamDriver connected to OVN NB`

## How It Works

1. **Image build**: Our Dockerfile installs both packages
2. **Entry point**: `pyproject.toml` registers `vpnv4_driver` with stevedore
3. **Agent startup**: Upstream agent calls `DriverManager(namespace='ovn_bgp_agent.drivers', name='vpnv4_driver')`
4. **Driver loads**: Stevedore finds our entry point and instantiates `VPNv4UpstreamDriver`
5. **Events**: Upstream agent's watchers call `expose_ip(ips, row)` → our driver extracts namespace → calls `VPNv4RouteDriver`

## Configuration Options

All VPNv4 options are registered in `config_extensions.py`:

- `vpnv4_output_dir` - Where FRR configs are written
- `vpnv4_rd_base` - Route Distinguisher base ASN
- `vpnv4_rt_base` - Route Target base ASN  
- `vpnv4_router_id` - Router ID for VPNv4 sessions
- `vpnv4_peers` - List of BGP peer strings

## Troubleshooting

**Driver not found:**
- Check image includes both packages
- Verify stevedore entry point in `pyproject.toml`
- Check logs for "Could not load driver" errors

**Namespace not found:**
- Check OVN NB DB connection
- Verify `row.external_ids` contains namespace keys
- Check logs for namespace extraction debug messages

**Config not applied:**
- Verify ConfigMap is mounted correctly
- Check `--config-file` argument points to correct path
- Verify INI format is correct (not YAML)

