"""Configuration extensions for VPNv4 driver in upstream ovn-bgp-agent.

This module registers additional oslo.config options that the VPNv4 driver
needs. These should be integrated into the upstream agent's config.py when
submitting a PR.
"""

from oslo_config import cfg

# VPNv4-specific configuration options
vpnv4_opts = [
    cfg.StrOpt('vpnv4_output_dir',
               default='/etc/frr/vpnv4',
               help='Directory where VPNv4 FRR configuration files are written.'),
    cfg.IntOpt('vpnv4_rd_base',
               default=None,
               help='Base ASN for Route Distinguisher allocation. '
                    'If not set, uses bgp_AS value.'),
    cfg.IntOpt('vpnv4_rt_base',
               default=None,
               help='Base ASN for Route Target allocation. '
                    'If not set, uses bgp_AS value.'),
    cfg.StrOpt('vpnv4_router_id',
               default=None,
               help='Router ID for VPNv4 BGP sessions. '
                    'If not set, uses bgp_router_id value.'),
    cfg.ListOpt('vpnv4_peers',
                default=[],
                help='List of VPNv4 BGP peer addresses in format: '
                     'address:remote_asn:description. '
                     'Example: ["10.0.0.1:65001:fortigate-1", "10.0.0.2:65001:fortigate-2"]'),
]


def register_vpnv4_opts():
    """Register VPNv4 configuration options with oslo.config.
    
    Registers options to the DEFAULT group for now. When integrated upstream,
    these could be moved to a dedicated 'vpnv4' group.
    """
    from ovn_bgp_agent import config as agent_config
    # Register to DEFAULT group (same as other agent_opts)
    agent_config.CONF.register_opts(vpnv4_opts)


def parse_vpnv4_peers(peer_list):
    """Parse VPNv4 peer list from config into Neighbor objects.
    
    Args:
        peer_list: List of strings in format "address:remote_asn:description"
        
    Returns:
        List of dicts with 'address', 'remote_asn', 'description' keys
    """
    peers = []
    for peer_str in peer_list:
        parts = peer_str.split(':')
        if len(parts) >= 2:
            peers.append({
                'address': parts[0],
                'remote_asn': int(parts[1]),
                'description': ':'.join(parts[2:]) if len(parts) > 2 else '',
            })
    return peers

