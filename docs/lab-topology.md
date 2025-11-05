# Lab Topology Blueprint — OVN-BGP VPNv4 POC

## 1. High-Level Layout

```
                        +--------------------------+
                        |  FortiGate Simulator PE  |
                        |  (GoBGP / custom agent)  |
                        +-----------+--------------+
                                    |
                              172.31.0.1/30
                                    |
                        +-----------+--------------+
                        |  FRR Container (per node) |
+-----------------------+-----------+---------------+------------------------+
|   Kubernetes Worker (kind)                                        |
|                                                                    |
|  +--------------------------+      +---------------------------+   |
|  | ovn-bgp-agent (vpnv4)    |<---->| OVN Controller Components |   |
|  +--------------------------+      +---------------------------+   |
|                                                                    |
|  Pod network namespaces (VRF per tenant)                           |
+--------------------------------------------------------------------+

Automation / operator host reaches all components via management network (default docker bridge or custom).
```

## 2. IP Plan

| Segment | Purpose | Example CIDR | Notes |
|---------|---------|--------------|-------|
| mgmt0 | Host ↔ containers | `172.20.0.0/16` | Provided by docker bridge |
| peering0 | FRR ↔ FortiGate simulator | `172.31.0.0/30` | `/30` per FRR instance; adjust per lab size |
| loopback_frr | FRR BGP router-id | `10.255.0.x/32` | Derived from worker index |
| tenant-net | OVN pod subnet | `192.168.X.0/24` | One per namespace/tenant |

> Adjust CIDRs if they conflict with your host network. Document overrides in `scripts/lab/env.example` (future task).

## 3. Component Placement

- **Simulated FortiGate** runs as a container on the host, attached to both `mgmt0` and `peering0` networks.
- **FRR** container runs alongside `ovn-bgp-agent` within the worker node namespace; `docker-compose` assigns it to the same networks.
- **kind cluster** hosts OVN/OVN-BGP components; CNI networking remains untouched except for BGP peering.

## 4. Control Plane Flows

1. `ovn-bgp-agent` discovers pod/service routes from OVN databases.
2. Driver programs FRR via CLI or config reload to advertise routes in VRF context.
3. FRR establishes MP-BGP sessions over `peering0` with the FortiGate simulator.
4. Simulator enforces RD/RT policies and exposes API for inspection.

## 5. Data Plane Assumptions

- Demo environment forwards traffic using plain IP; MPLS labels are advertised but not switched.
- Pod-to-simulator ping tests traverse worker host routing tables; no SR-IOV or hardware acceleration assumed.

## 6. Next Steps

- Encode this topology in `docker-compose.yaml` (Milestone 1).
- Generate diagrams (e.g., draw.io) if visual assets are required for presentations.

