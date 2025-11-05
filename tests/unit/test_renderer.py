from pathlib import Path

from ovn_bgp_vpnv4.config import AddressFamily, GlobalConfig, Neighbor, TenantContext, VRFDefinition
from ovn_bgp_vpnv4.frr import FRRConfigRenderer


def build_config(tmp_path: Path) -> GlobalConfig:
    return GlobalConfig(
        local_asn=65000,
        router_id="10.0.0.1",
        rd_base=65000,
        rt_base=65000,
        neighbours=[
            Neighbor(
                address="172.31.100.11",
                remote_asn=65100,
                families=(AddressFamily.VPNV4,),
                description="FortiGate-sim",
            )
        ],
    )


def test_renderer_writes_file(tmp_path: Path):
    config = build_config(tmp_path)
    renderer = FRRConfigRenderer(config, tmp_path, include_globals=True)

    tenant = TenantContext(
        namespace="tenant-a",
        vrf=VRFDefinition(
            name="tenant-a",
            rd="65000:100",
            import_rts=["65000:100"],
            export_rts=["65000:100"],
        ),
        advertised_prefixes=["10.244.0.0/24"],
    )

    result = renderer.render([tenant])

    assert result.output_path.exists()
    content = result.output_path.read_text()
    assert "router bgp 65000" in content
    assert "neighbor 172.31.100.11 remote-as 65100" in content
    assert "network 10.244.0.0/24" in content

