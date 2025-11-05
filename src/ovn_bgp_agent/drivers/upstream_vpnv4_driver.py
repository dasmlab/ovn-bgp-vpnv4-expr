"""Upstream ovn-bgp-agent driver adapter for VPNv4.

This module provides a driver that implements the upstream AgentDriverBase
interface, allowing the VPNv4 driver to be loaded by the upstream
ovn-bgp-agent service via stevedore entry points.
"""

from __future__ import annotations

import logging
import ipaddress
from pathlib import Path
from typing import Optional, List, Dict, Set
from threading import Lock, Thread, Event
import time

from ovn_bgp_agent.drivers import driver_api
from ovn_bgp_agent import config as agent_config
from ovn_bgp_agent.drivers.openstack.utils import ovn as ovn_utils
from ovn_bgp_agent.utils import linux_net
import pyroute2

from ovn_bgp_vpnv4.driver import VPNv4RouteDriver
from ovn_bgp_vpnv4.config import GlobalConfig, Neighbor, AddressFamily

# Try to register VPNv4 config options if available
try:
    from ovn_bgp_agent.config_extensions import register_vpnv4_opts, parse_vpnv4_peers
    register_vpnv4_opts()
except ImportError:
    # Config extensions not available - use defaults
    def parse_vpnv4_peers(peer_list):
        return []

LOG = logging.getLogger(__name__)

# Namespace keys to check in external_ids (in order of preference)
NAMESPACE_KEYS = (
    "k8s.ovn.org/namespace",
    "k8s.ovn.org/namespace_name",
    "k8s.ovn.org/project",
    "neutron:project_id",
    "namespace",
)

# BGP protocol number (from netlink constants)
# From /usr/include/linux/rtnetlink.h: RTPROT_BGP = 186
RTPROT_BGP = 186


class VPNv4UpstreamDriver(driver_api.AgentDriverBase):
    """Upstream agent driver that wraps VPNv4RouteDriver.

    This driver adapts the namespace-oriented VPNv4RouteDriver to the
    IP-oriented AgentDriverBase interface expected by ovn-bgp-agent.
    It aggregates IPs by namespace and uses the VPNv4RouteDriver to
    manage VRF-level route advertisements.
    
    Additionally, it monitors imported routes from FortiGate peers
    and syncs them to OVN logical routers.
    """

    def __init__(self):
        """Initialize the VPNv4 driver with configuration from ovn-bgp-agent."""
        super().__init__()
        
        # Load configuration from ovn-bgp-agent config
        # The upstream agent uses oslo.config
        output_dir = getattr(agent_config.CONF, 'vpnv4_output_dir', '/etc/frr/vpnv4')
        self._output_dir = Path(output_dir)
        
        # Build global config from upstream agent config
        global_config = self._build_global_config()
        
        # Initialize the VPNv4 route driver
        self._driver = VPNv4RouteDriver(
            global_config,
            output_dir=self._output_dir,
            include_globals=True,
        )
        
        # Track IPs per namespace for aggregation
        self._namespace_ips: dict[str, set[str]] = {}
        
        # OVN NB IDL for namespace lookup and route sync (initialized in start())
        self._nb_idl: Optional[ovn_utils.OvnNbIdl] = None
        
        # Track imported routes per namespace: {namespace: {prefix: next_hop}}
        self._imported_routes: Dict[str, Dict[str, str]] = {}
        self._routes_lock = Lock()
        
        # Route import watcher thread
        self._route_watcher_thread: Optional[Thread] = None
        self._stop_event = Event()
        
        LOG.info("VPNv4UpstreamDriver initialized (output=%s)", self._output_dir)

    def _build_global_config(self) -> GlobalConfig:
        """Build GlobalConfig from upstream agent configuration."""
        # Extract VPNv4 settings from oslo.config
        # Use BGP settings from upstream agent as defaults
        local_asn = int(getattr(agent_config.CONF, 'bgp_AS', 65000))
        router_id = getattr(agent_config.CONF, 'bgp_router_id') or getattr(
            agent_config.CONF, 'vpnv4_router_id', '10.255.0.2')
        
        # VPNv4-specific settings
        rd_base = getattr(agent_config.CONF, 'vpnv4_rd_base', None) or local_asn
        rt_base = getattr(agent_config.CONF, 'vpnv4_rt_base', None) or local_asn
        router_id = getattr(agent_config.CONF, 'vpnv4_router_id', None) or router_id
        peer_list = getattr(agent_config.CONF, 'vpnv4_peers', [])
        
        # Build neighbor list from config
        neighbors = []
        if peer_list:
            parsed_peers = parse_vpnv4_peers(peer_list)
            for peer in parsed_peers:
                neighbors.append(Neighbor(
                    address=peer.get('address'),
                    remote_asn=peer.get('remote_asn', local_asn),
                    families=[AddressFamily.VPNV4],
                    description=peer.get('description', ''),
                ))
        
        return GlobalConfig(
            local_asn=local_asn,
            router_id=router_id,
            rd_base=rd_base,
            rt_base=rt_base,
            neighbours=neighbors,
        )

    def start(self):
        """Start the VPNv4 driver and initialize OVN connections."""
        LOG.info("VPNv4UpstreamDriver starting")
        
        # Initialize OVN NB IDL for namespace lookups and route sync
        # Get OVN remote from OVS connection
        ovs_idl = ovn_utils.OvsIdl()
        ovs_idl.start(agent_config.CONF.ovsdb_connection)
        ovn_remote = ovs_idl.get_ovn_remote()
        ovs_idl.stop()
        
        if ovn_remote:
            # Initialize NB IDL for namespace lookups and route installation
            # start() returns the OvsdbNbOvnIdl object
            nb_idl_instance = ovn_utils.OvnNbIdl(ovn_remote)
            self._nb_idl = nb_idl_instance.start()
            LOG.info("VPNv4UpstreamDriver connected to OVN NB: %s", ovn_remote)
        else:
            LOG.warning("VPNv4UpstreamDriver: Could not determine OVN remote")
        
        # Start route import watcher
        self._start_route_watcher()
        
        LOG.info("VPNv4UpstreamDriver started")
    
    def stop(self):
        """Stop the VPNv4 driver and cleanup resources."""
        LOG.info("VPNv4UpstreamDriver stopping")
        self._stop_event.set()
        if self._route_watcher_thread:
            self._route_watcher_thread.join(timeout=5)
        if self._nb_idl:
            self._nb_idl.stop()
        LOG.info("VPNv4UpstreamDriver stopped")

    def sync(self):
        """Reconcile routes to ensure consistency."""
        LOG.debug("VPNv4UpstreamDriver sync called")
        self._driver.sync()
        # Also sync imported routes
        self._sync_imported_routes()

    def frr_sync(self):
        """Reconcile FRR configuration."""
        LOG.debug("VPNv4UpstreamDriver frr_sync called")
        # The driver's render() method updates FRR config
        # We could trigger a reload here if needed
        self._driver.render()

    def expose_ip(self, ips, row, associated_port=None):
        """Expose IP addresses via VPNv4.
        
        Args:
            ips: List of IP address strings to expose
            row: OVN Port_Binding row object from SB DB
            associated_port: Optional associated port row
        
        The upstream agent calls this with a list of IPs and a Port_Binding row.
        We extract namespace and aggregate IPs per namespace.
        """
        if not ips:
            return []
        
        # Normalize IPs to list of strings
        if isinstance(ips, str):
            ip_list = [ips]
        else:
            ip_list = [str(ip) for ip in ips]
        
        # Extract namespace from row
        namespace = self._extract_namespace(row)
        
        if not namespace:
            LOG.debug("expose_ip: namespace not found for IPs %s (logical_port=%s)", 
                      ip_list, row.logical_port if row else "None")
            return []
        
        # Aggregate IPs per namespace
        if namespace not in self._namespace_ips:
            self._namespace_ips[namespace] = set()
        
        for ip_str in ip_list:
            # Normalize to /32 or /128
            if '/' not in ip_str:
                ip_str = f"{ip_str}/32" if ':' not in ip_str else f"{ip_str}/128"
            self._namespace_ips[namespace].add(ip_str)
        
        # Update VPNv4 driver with all IPs for this namespace
        prefixes = sorted(self._namespace_ips[namespace])
        self._driver.synchronize_prefixes(namespace, prefixes)
        LOG.debug("expose_ip: namespace=%s, ips=%s, total_prefixes=%d", 
                 namespace, ip_list, len(prefixes))
        
        return ip_list

    def withdraw_ip(self, ips, row, associated_port=None):
        """Withdraw IP addresses from VPNv4 advertisement.
        
        Args:
            ips: List of IP address strings to withdraw
            row: OVN Port_Binding row object from SB DB
            associated_port: Optional associated port row
        """
        if not ips:
            return
        
        # Normalize IPs to list of strings
        if isinstance(ips, str):
            ip_list = [ips]
        else:
            ip_list = [str(ip) for ip in ips]
        
        # Extract namespace from row
        namespace = self._extract_namespace(row)
        
        if not namespace:
            # Try to find namespace by searching our tracked IPs
            for ns, tracked_ips in self._namespace_ips.items():
                for ip_str in ip_list:
                    normalized = ip_str if '/' in ip_str else (
                        f"{ip_str}/32" if ':' not in ip_str else f"{ip_str}/128")
                    if normalized in tracked_ips:
                        namespace = ns
                        break
                if namespace:
                    break
        
        if not namespace:
            LOG.debug("withdraw_ip: namespace not found for IPs %s", ip_list)
            return
        
        # Remove IPs from namespace tracking
        for ip_str in ip_list:
            normalized = ip_str if '/' in ip_str else (
                f"{ip_str}/32" if ':' not in ip_str else f"{ip_str}/128")
            self._namespace_ips[namespace].discard(normalized)
        
        # Update VPNv4 driver
        if self._namespace_ips[namespace]:
            prefixes = sorted(self._namespace_ips[namespace])
            self._driver.synchronize_prefixes(namespace, prefixes)
        else:
            # No more IPs for this namespace - withdraw namespace
            self._driver.withdraw_namespace(namespace)
            del self._namespace_ips[namespace]
        
        LOG.debug("withdraw_ip: namespace=%s, ips=%s", namespace, ip_list)

    def expose_remote_ip(self, ip_address):
        """Expose a remote IP (imported route).
        
        This is called when the upstream agent detects a remote route
        that should be imported. However, for VPNv4, we handle route
        import differently - we monitor kernel VRF tables directly.
        """
        LOG.debug("expose_remote_ip called (VPNv4 uses direct VRF monitoring): %s", ip_address)

    def withdraw_remote_ip(self, ip_address):
        """Withdraw a remote IP.
        
        This is called when a remote route should be withdrawn.
        For VPNv4, we handle route withdrawal via VRF monitoring.
        """
        LOG.debug("withdraw_remote_ip called (VPNv4 uses direct VRF monitoring): %s", ip_address)

    def expose_subnet(self, subnet):
        """Expose a subnet - VPNv4 works at IP level, so this is a no-op."""
        LOG.debug("expose_subnet called (VPNv4 works at IP level): %s", subnet)

    def withdraw_subnet(self, subnet):
        """Withdraw a subnet - VPNv4 works at IP level, so this is a no-op."""
        LOG.debug("withdraw_subnet called (VPNv4 works at IP level): %s", subnet)
    
    def _extract_namespace(self, row) -> Optional[str]:
        """Extract namespace from OVN row object.
        
        Tries multiple approaches:
        1. Check row.external_ids for namespace keys
        2. Query OVN NB DB Logical_Switch_Port by logical_port name
        
        Args:
            row: OVN Port_Binding row from SB DB
            
        Returns:
            Namespace name or None if not found
        """
        if not row:
            return None
        
        # First, try external_ids on the row itself
        if hasattr(row, 'external_ids') and row.external_ids:
            for key in NAMESPACE_KEYS:
                namespace = row.external_ids.get(key)
                if namespace:
                    LOG.debug("Found namespace '%s' from row.external_ids[%s]", 
                             namespace, key)
                    return namespace
        
        # If not found, query NB DB for Logical_Switch_Port
        if hasattr(row, 'logical_port') and self._nb_idl:
            try:
                # Use db_find_rows to find Logical_Switch_Port by name
                cmd = self._nb_idl.db_find_rows(
                    'Logical_Switch_Port', ('name', '=', row.logical_port))
                lsp_rows = cmd.execute(check_error=True)
                if lsp_rows:
                    lsp = lsp_rows[0]
                    if hasattr(lsp, 'external_ids') and lsp.external_ids:
                        for key in NAMESPACE_KEYS:
                            namespace = lsp.external_ids.get(key)
                            if namespace:
                                LOG.debug("Found namespace '%s' from NB DB LSP[%s]", 
                                         namespace, key)
                                return namespace
            except Exception as e:
                LOG.debug("Could not lookup namespace from NB DB: %s", e)
        
        return None
    
    def _start_route_watcher(self):
        """Start background thread to monitor imported routes in VRF tables."""
        if self._route_watcher_thread:
            return
        
        self._route_watcher_thread = Thread(
            target=self._watch_imported_routes,
            daemon=True,
            name="VPNv4RouteWatcher"
        )
        self._route_watcher_thread.start()
        LOG.info("Started VPNv4 route import watcher")
    
    def _watch_imported_routes(self):
        """Background thread that monitors BGP routes in VRF tables and syncs to OVN."""
        poll_interval = getattr(agent_config.CONF, 'vpnv4_route_poll_interval', 30)
        
        while not self._stop_event.is_set():
            try:
                self._sync_imported_routes()
            except Exception as e:
                LOG.exception("Error syncing imported routes: %s", e)
            
            # Wait for next poll or stop signal
            self._stop_event.wait(poll_interval)
        
        LOG.info("VPNv4 route import watcher stopped")
    
    def _sync_imported_routes(self):
        """Sync imported routes from kernel VRF tables to OVN logical routers.
        
        For each namespace with a VRF:
        1. Read BGP routes from the VRF's routing table
        2. Compare with current imported routes
        3. Add/update/delete routes in OVN logical router
        """
        if not self._nb_idl:
            LOG.debug("OVN NB IDL not available, skipping route sync")
            return
        
        # Get all active namespaces with VRFs
        tenants = self._driver.list_tenants()
        if not tenants:
            return
        
        for tenant in tenants:
            namespace = tenant.namespace
            vrf_name = tenant.vrf.name
            
            try:
                # Get VRF table ID
                vrf_table = self._get_vrf_table(vrf_name)
                if vrf_table is None:
                    continue
                
                # Read BGP routes from VRF
                current_routes = self._get_bgp_routes_from_vrf(vrf_table)
                
                # Get existing imported routes for this namespace
                with self._routes_lock:
                    existing_routes = self._imported_routes.get(namespace, {})
                
                # Find changes
                current_prefixes = set(current_routes.keys())
                existing_prefixes = set(existing_routes.keys())
                
                adds = current_prefixes - existing_prefixes
                updates = {p: current_routes[p] for p in current_prefixes & existing_prefixes 
                          if current_routes[p] != existing_routes[p]}
                deletes = existing_prefixes - current_prefixes
                
                if adds or updates or deletes:
                    LOG.info("Syncing routes for namespace '%s': +%d ~%d -%d",
                            namespace, len(adds), len(updates), len(deletes))
                    
                    # Update OVN logical router
                    self._sync_routes_to_ovn(namespace, adds | set(updates.keys()), 
                                            current_routes, deletes)
                    
                    # Update our tracking
                    with self._routes_lock:
                        self._imported_routes[namespace] = current_routes.copy()
                
            except Exception as e:
                LOG.exception("Error syncing routes for namespace '%s': %s", 
                             namespace, e)
    
    def _get_vrf_table(self, vrf_name: str) -> Optional[int]:
        """Get routing table ID for a VRF device."""
        try:
            with pyroute2.IPRoute() as ipr:
                links = ipr.link_lookup(ifname=vrf_name)
                if not links:
                    return None
                link_info = ipr.get_links(links[0])[0]
                # VRF table is in IFLA_INFO_DATA -> IFLA_VRF_TABLE
                info_data = link_info.get_attr('IFLA_INFO_DATA')
                if info_data:
                    table = info_data.get_attr('IFLA_VRF_TABLE')
                    return table
        except Exception as e:
            LOG.debug("Could not get VRF table for %s: %s", vrf_name, e)
        return None
    
    def _get_bgp_routes_from_vrf(self, table_id: int) -> Dict[str, str]:
        """Read BGP routes from a VRF routing table.
        
        Returns:
            Dict mapping prefix (CIDR) to next_hop IP
        """
        routes = {}
        try:
            with pyroute2.IPRoute() as ipr:
                # Filter routes by table and protocol
                filter_route = {'table': table_id, 'protocol': RTPROT_BGP}
                vrf_routes = ipr.get_routes(**filter_route)
                
                for route in vrf_routes:
                    # Extract destination prefix
                    dst = route.get_attr('RTA_DST')
                    if not dst:
                        continue
                    
                    # Get prefix length
                    prefixlen = route.get('dst_len', 32)
                    if route.get('family') == 10:  # AF_INET6
                        prefixlen = route.get('dst_len', 128)
                    
                    prefix = f"{dst}/{prefixlen}"
                    
                    # Extract next hop
                    gw = route.get_attr('RTA_GATEWAY')
                    if not gw:
                        continue
                    
                    routes[prefix] = str(gw)
        except Exception as e:
            LOG.debug("Error reading BGP routes from table %d: %s", table_id, e)
        
        return routes
    
    def _sync_routes_to_ovn(self, namespace: str, add_prefixes: Set[str],
                           routes: Dict[str, str], delete_prefixes: Set[str]):
        """Sync routes to OVN logical router for a namespace.
        
        Args:
            namespace: Kubernetes namespace name
            add_prefixes: Set of prefixes to add/update
            routes: Dict mapping prefix to next_hop
            delete_prefixes: Set of prefixes to delete
        """
        if not self._nb_idl:
            return
        
        # Find logical router for this namespace
        # In OVN-Kubernetes, gateway routers are named GR_<node_name>
        # For now, we'll need to find the router associated with this namespace
        # This is a simplified approach - may need refinement based on actual OVN setup
        
        # Try to find namespace router by looking for router with namespace in external_ids
        # or by convention: for default network, use cluster router
        router_name = self._find_namespace_router(namespace)
        if not router_name:
            LOG.debug("Could not find OVN router for namespace '%s'", namespace)
            return
        
        try:
            # Build OVSDB operations
            ops = []
            
            # Add/update routes
            for prefix in add_prefixes:
                next_hop = routes.get(prefix)
                if not next_hop:
                    continue
                
                # Create LogicalRouterStaticRoute
                # Note: We need to determine the output port - this depends on
                # the OVN gateway setup. For now, we'll use a placeholder.
                # In production, this should be determined from the gateway router config.
                lrsr = {
                    'IPPrefix': prefix,
                    'Nexthop': next_hop,
                    'ExternalIDs': {
                        'vpnv4-driver': 'true',
                        'namespace': namespace,
                    }
                }
                
                    # Use OVN NB API to add route
                    try:
                        self._nb_idl.lr_route_add(
                            router_name,
                            prefix,
                            next_hop,
                            may_exist=True  # Allow updating existing route
                        ).execute(check_error=True)
                        LOG.info("Added route to OVN router %s: %s via %s",
                                router_name, prefix, next_hop)
                    except Exception as e:
                        LOG.exception("Error adding route %s to router %s: %s",
                                    prefix, router_name, e)
            
            # Delete routes
            for prefix in delete_prefixes:
                try:
                    self._nb_idl.lr_route_del(
                        router_name,
                        prefix,
                        if_exists=True  # Don't error if route doesn't exist
                    ).execute(check_error=True)
                    LOG.info("Deleted route from OVN router %s: %s",
                            router_name, prefix)
                except Exception as e:
                    LOG.exception("Error deleting route %s from router %s: %s",
                                prefix, router_name, e)
                    
        except Exception as e:
            LOG.exception("Error syncing routes to OVN for namespace '%s': %s",
                         namespace, e)
    
    def _find_namespace_router(self, namespace: str) -> Optional[str]:
        """Find OVN logical router for a namespace.
        
        In OVN-Kubernetes:
        - Default network uses 'ovn-cluster-router'
        - User-defined networks may have gateway routers named GR_<node_name>
        - For now, we use a simple mapping: try to find router with namespace in external_ids
        
        Returns:
            Router name or None if not found
        """
        if not self._nb_idl:
            return None
        
        # For default network, use cluster router
        if namespace == 'default' or namespace.startswith('kube-'):
            try:
                # Verify router exists
                self._nb_idl.lr_get('ovn-cluster-router').execute(check_error=True)
                return 'ovn-cluster-router'
            except Exception:
                pass
        
        # For other namespaces, try to find router with namespace in external_ids
        # This is a simplified approach - may need refinement
        try:
            # Query Logical_Router table for routers with namespace in external_ids
            # Note: This may not work for all OVN-Kubernetes setups
            # A more robust approach would query based on network name or CUDN
            LOG.debug("Looking for router for namespace '%s'", namespace)
            # For now, return None - route import may need namespace->router mapping
            # from OVN-Kubernetes configuration
            return None
        except Exception as e:
            LOG.debug("Error finding router for namespace '%s': %s", namespace, e)
            return None
