"""Upstream ovn-bgp-agent driver adapter for VPNv4.

This module provides a driver that implements the upstream AgentDriverBase
interface, allowing the VPNv4 driver to be loaded by the upstream
ovn-bgp-agent service via stevedore entry points.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, List

from ovn_bgp_agent.drivers import driver_api
from ovn_bgp_agent import config as agent_config
from ovn_bgp_agent.drivers.openstack.utils import ovn as ovn_utils

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


class VPNv4UpstreamDriver(driver_api.AgentDriverBase):
    """Upstream agent driver that wraps VPNv4RouteDriver.

    This driver adapts the namespace-oriented VPNv4RouteDriver to the
    IP-oriented AgentDriverBase interface expected by ovn-bgp-agent.
    It aggregates IPs by namespace and uses the VPNv4RouteDriver to
    manage VRF-level route advertisements.
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
        
        # OVN NB IDL for namespace lookup (initialized in start())
        self._nb_idl: Optional[ovn_utils.OvnNbIdl] = None
        
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
        
        # Initialize OVN NB IDL for namespace lookups
        # Get OVN remote from OVS connection
        ovs_idl = ovn_utils.OvsIdl()
        ovs_idl.start(agent_config.CONF.ovsdb_connection)
        ovn_remote = ovs_idl.get_ovn_remote()
        ovs_idl.stop()
        
        if ovn_remote:
            # Initialize NB IDL for namespace lookups
            # start() returns the OvsdbNbOvnIdl object
            nb_idl_instance = ovn_utils.OvnNbIdl(ovn_remote)
            self._nb_idl = nb_idl_instance.start()
            LOG.info("VPNv4UpstreamDriver connected to OVN NB: %s", ovn_remote)
        else:
            LOG.warning("VPNv4UpstreamDriver: Could not determine OVN remote")
        
        LOG.info("VPNv4UpstreamDriver started")

    def sync(self):
        """Reconcile routes to ensure consistency."""
        LOG.debug("VPNv4UpstreamDriver sync called")
        self._driver.sync()

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
        """Expose a remote IP (imported route) - not applicable for VPNv4 export."""
        LOG.debug("expose_remote_ip called (not applicable for VPNv4 export): %s", ip_address)

    def withdraw_remote_ip(self, ip_address):
        """Withdraw a remote IP - not applicable for VPNv4 export."""
        LOG.debug("withdraw_remote_ip called (not applicable for VPNv4 export): %s", ip_address)

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

