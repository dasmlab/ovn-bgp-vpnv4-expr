"""Upstream ovn-bgp-agent driver adapter for VPNv4.

This module provides a driver that implements the upstream AgentDriverBase
interface, allowing the VPNv4 driver to be loaded by the upstream
ovn-bgp-agent service via stevedore entry points.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from ovn_bgp_agent.drivers import driver_api
from ovn_bgp_agent import config as agent_config

from ovn_bgp_vpnv4.driver import VPNv4RouteDriver
from ovn_bgp_vpnv4.config import GlobalConfig, Neighbor, AddressFamily

LOG = logging.getLogger(__name__)


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
        # The upstream agent uses oslo.config, so we need to extract
        # VPNv4-specific settings from the config
        self._config_path = Path(agent_config.CONF.vpnv4_config_file)
        self._output_dir = Path(agent_config.CONF.vpnv4_output_dir)
        
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
        
        LOG.info("VPNv4UpstreamDriver initialized (config=%s, output=%s)", 
                 self._config_path, self._output_dir)

    def _build_global_config(self) -> GlobalConfig:
        """Build GlobalConfig from upstream agent configuration."""
        # Extract VPNv4 settings from oslo.config
        # For now, use defaults - these should be configurable via
        # upstream agent config options
        local_asn = getattr(agent_config.CONF, 'vpnv4_local_asn', 65000)
        router_id = getattr(agent_config.CONF, 'vpnv4_router_id', '10.255.0.2')
        rd_base = getattr(agent_config.CONF, 'vpnv4_rd_base', 65000)
        rt_base = getattr(agent_config.CONF, 'vpnv4_rt_base', 65000)
        
        # Build neighbor list from config
        neighbors = []
        for peer in getattr(agent_config.CONF, 'vpnv4_peers', []):
            neighbors.append(Neighbor(
                address=peer.address,
                remote_asn=peer.remote_asn,
                families=[AddressFamily.VPNV4],
                description=peer.description,
            ))
        
        return GlobalConfig(
            local_asn=local_asn,
            router_id=router_id,
            rd_base=rd_base,
            rt_base=rt_base,
            neighbours=neighbors,
        )

    def start(self):
        """Start the VPNv4 driver (no-op for now, initialization in __init__)."""
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

    def expose_ip(self, ip_address, row=None):
        """Expose an IP address via VPNv4.
        
        Args:
            ip_address: IP address to expose (string or object with .ip attribute)
            row: Optional OVN row object (Port_Binding) that may contain namespace info
        
        The upstream agent calls this with IP addresses. We need to:
        1. Extract namespace from row.external_ids if available
        2. Or query OVN NB DB to find namespace for this IP
        3. Aggregate IPs per namespace
        4. Call synchronize_prefixes when namespace is known
        """
        # Extract IP string
        ip_str = str(ip_address.ip) if hasattr(ip_address, 'ip') else str(ip_address)
        
        # Try to extract namespace from row external_ids
        namespace = None
        if row and hasattr(row, 'external_ids'):
            namespace = row.external_ids.get('k8s.ovn.org/namespace') or \
                       row.external_ids.get('k8s.ovn.org/namespace_name')
        
        if not namespace:
            # TODO: Query OVN NB DB to find namespace for this IP
            # This requires implementing OVN NB DB lookup by IP
            LOG.warning("expose_ip: namespace not found for IP %s (row=%s)", 
                       ip_str, row if row else "None")
            return
        
        # Aggregate IPs per namespace
        if namespace not in self._namespace_ips:
            self._namespace_ips[namespace] = set()
        self._namespace_ips[namespace].add(ip_str)
        
        # Update VPNv4 driver with all IPs for this namespace
        prefixes = sorted(self._namespace_ips[namespace])
        self._driver.synchronize_prefixes(namespace, prefixes)
        LOG.debug("expose_ip: namespace=%s, ip=%s, total_prefixes=%d", 
                 namespace, ip_str, len(prefixes))

    def withdraw_ip(self, ip_address, row=None):
        """Withdraw an IP address from VPNv4 advertisement.
        
        Args:
            ip_address: IP address to withdraw
            row: Optional OVN row object (Port_Binding) that may contain namespace info
        """
        ip_str = str(ip_address.ip) if hasattr(ip_address, 'ip') else str(ip_address)
        
        # Try to extract namespace from row external_ids
        namespace = None
        if row and hasattr(row, 'external_ids'):
            namespace = row.external_ids.get('k8s.ovn.org/namespace') or \
                       row.external_ids.get('k8s.ovn.org/namespace_name')
        
        if not namespace:
            # Try to find namespace by searching our tracked IPs
            for ns, ips in self._namespace_ips.items():
                if ip_str in ips:
                    namespace = ns
                    break
        
        if not namespace:
            LOG.warning("withdraw_ip: namespace not found for IP %s", ip_str)
            return
        
        # Remove IP from namespace tracking
        if namespace in self._namespace_ips:
            self._namespace_ips[namespace].discard(ip_str)
            
            # Update VPNv4 driver
            if self._namespace_ips[namespace]:
                prefixes = sorted(self._namespace_ips[namespace])
                self._driver.synchronize_prefixes(namespace, prefixes)
            else:
                # No more IPs for this namespace - withdraw namespace
                self._driver.withdraw_namespace(namespace)
                del self._namespace_ips[namespace]
        
        LOG.debug("withdraw_ip: namespace=%s, ip=%s", namespace, ip_str)

    def expose_remote_ip(self, ip_address):
        """Expose a remote IP (imported route) - not applicable for VPNv4 export."""
        LOG.debug("expose_remote_ip called (not applicable for VPNv4 export): %s", ip_address)

    def withdraw_remote_ip(self, ip_address):
        """Withdraw a remote IP - not applicable for VPNv4 export."""
        LOG.debug("withdraw_remote_ip called (not applicable for VPNv4 export): %s", ip_address)

    def expose_subnet(self, subnet):
        """Expose a subnet - not directly applicable for VPNv4 per-IP model."""
        LOG.debug("expose_subnet called: %s", subnet)

    def withdraw_subnet(self, subnet):
        """Withdraw a subnet."""
        LOG.debug("withdraw_subnet called: %s", subnet)

