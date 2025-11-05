# Upstream ovn-bgp-agent Integration

## Current Status

We have **two separate implementations**:

1. **Standalone `vpnv4-agent`** ✅ - Fully working with OVN watcher
   - Located in `src/vpnv4_agent/`
   - Uses namespace-oriented API (`NamespaceUpsert`/`NamespaceDelete`)
   - Polls OVN NB DB directly
   - Ready for production use

2. **Upstream `ovn-bgp-agent` integration** ✅ - **Implemented with bidirectional route handling**
   - Implemented `AgentDriverBase` interface in `VPNv4UpstreamDriver`
   - Adapts IP-oriented API (`expose_ip(ips, row)`/`withdraw_ip(ips, row)`) to namespace-oriented VPNv4 driver
   - Registered as stevedore entry point (`vpnv4_driver`)
   - Extracts namespace from `row.external_ids` or queries OVN NB DB
   - Registered oslo.config options for VPNv4 settings
   - **Route export:** Advertises namespace prefixes to FortiGate via VPNv4
   - **Route import:** Monitors kernel VRF tables for BGP routes from FortiGate and syncs them to OVN logical routers
   - **Ready for testing with upstream agent service**

## The Integration Challenge

The upstream `ovn-bgp-agent` has a **different architecture**:

### Upstream Agent Architecture
```
ovn-bgp-agent (main service)
  └─> Loads driver via stevedore (namespace: ovn_bgp_agent.drivers)
      └─> Driver implements AgentDriverBase interface
          ├─> expose_ip(ip_address)
          ├─> withdraw_ip(ip_address)
          ├─> expose_subnet(subnet)
          └─> Uses OVN SB IDL watchers for events
```

### Our VPNv4 Driver Architecture
```
vpnv4-agent (standalone)
  └─> Namespace-oriented API
      ├─> on_namespace_upsert(namespace, prefixes)
      ├─> on_namespace_delete(namespace)
      └─> Uses OVN NB DB poller for namespace discovery
```

### Key Differences

1. **API Mismatch:**
   - Upstream: `expose_ip(ip)` - IP-first, driver must determine namespace
   - Our driver: `synchronize_prefixes(namespace, [ips])` - Namespace-first

2. **Event Source:**
   - Upstream: Uses OVN SB IDL watchers (Port_Binding events)
   - Our driver: Uses OVN NB DB poller (Logical_Switch_Port aggregation)

3. **Configuration:**
   - Upstream: Uses oslo.config (Python config system)
   - Our driver: Uses YAML config files

## What Needs to Be Done

### Option 1: Create Upstream-Compatible Driver (Recommended for PR)

Create a new driver class that implements `AgentDriverBase`:

```python
class VPNv4UpstreamDriver(AgentDriverBase):
    def __init__(self):
        # Initialize VPNv4RouteDriver internally
        self._vpnv4_driver = VPNv4RouteDriver(...)
        self._namespace_ips = {}  # Track IPs per namespace
        
    def expose_ip(self, ip_address):
        # Extract namespace from IP context
        # Aggregate IPs per namespace
        # Call self._vpnv4_driver.synchronize_prefixes(namespace, [ips])
        
    def withdraw_ip(self, ip_address):
        # Remove IP from namespace tracking
        # Update VPNv4 driver
```

**Requirements:**
- Extract namespace information from IP context (may require upstream agent changes)
- Implement stevedore entry point registration
- Add oslo.config options for VPNv4 settings
- Handle OVN SB IDL events (if needed) or extend to use NB DB

### Option 2: Use Standalone Agent (Current Approach)

Continue using the standalone `vpnv4-agent` for now:
- ✅ Already working and tested
- ✅ Can be deployed alongside or instead of upstream agent
- ✅ Simpler architecture
- ⚠️ Requires separate DaemonSet deployment

### Option 3: Hybrid Approach

- Use standalone agent for production clusters
- Work on upstream integration in parallel
- Submit upstream PR when integration is complete

## Implementation Steps for Upstream Integration

### Step 1: Register Entry Point ✅

Added to `pyproject.toml`:

```toml
[project.entry-points."ovn_bgp_agent.drivers"]
vpnv4_driver = "ovn_bgp_agent.drivers.upstream_vpnv4_driver:VPNv4UpstreamDriver"
```

### Step 2: Implement AgentDriverBase Interface ✅

Created `src/ovn_bgp_agent/drivers/upstream_vpnv4_driver.py`:
- Inherits from `AgentDriverBase`
- Implements all abstract methods:
  - `expose_ip(ips, row, associated_port=None)` - extracts namespace, aggregates IPs
  - `withdraw_ip(ips, row, associated_port=None)` - removes IPs from namespace tracking
  - `expose_remote_ip()` / `withdraw_remote_ip()` - no-ops (not applicable)
  - `expose_subnet()` / `withdraw_subnet()` - no-ops (works at IP level)
  - `start()` - initializes OVN NB IDL for namespace lookups
  - `sync()` / `frr_sync()` - reconciliation methods
- Wraps `VPNv4RouteDriver` internally
- Extracts namespace from `row.external_ids` or queries OVN NB DB

### Step 3: Add Configuration Options ✅

Created `src/ovn_bgp_agent/config_extensions.py`:
- Registers VPNv4 options with oslo.config:
  - `vpnv4_output_dir` - FRR config output directory
  - `vpnv4_rd_base` - Route Distinguisher base ASN
  - `vpnv4_rt_base` - Route Target base ASN
  - `vpnv4_router_id` - Router ID for VPNv4 sessions
  - `vpnv4_peers` - List of BGP peers (format: "address:remote_asn:description")

### Step 4: Handle Namespace Extraction ✅

**Solution implemented:**
1. Check `row.external_ids` for namespace keys (`k8s.ovn.org/namespace`, etc.)
2. If not found, query OVN NB DB `Logical_Switch_Port` by `logical_port` name
3. Extract namespace from LSP `external_ids`
4. Fallback: Track IPs in memory and use for withdrawal if namespace not found

### Step 5: Testing 🚧

**Remaining:**
- Test with upstream agent's event system
- Verify FRR config generation
- Test route advertisement/withdrawal
- Validate with FortiGate peers

## Current Recommendation

**For k3s/OCP testing:** Use the standalone `vpnv4-agent` (already implemented)

**For upstream PR:** Implement Option 1 above, but this requires:
1. Understanding how upstream agent provides namespace context
2. Possibly extending upstream agent API
3. Coordinating with upstream maintainers

## Files Created

- `src/ovn_bgp_agent/drivers/upstream_vpnv4_driver.py` - Skeleton implementation
- This document - Integration analysis

## Next Steps

1. **Test standalone agent on k3s/OCP** (ready now)
2. **Investigate upstream agent's namespace context** - Check how existing drivers handle this
3. **Coordinate with upstream maintainers** - Discuss integration approach
4. **Implement full upstream driver** - Once namespace extraction is understood

