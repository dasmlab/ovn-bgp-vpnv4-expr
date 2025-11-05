from pathlib import Path

from ovn_bgp_vpnv4.config import AddressFamily, GlobalConfig, Neighbor
from ovn_bgp_vpnv4.driver import VPNv4RouteDriver


def build_driver(tmp_path: Path) -> VPNv4RouteDriver:
    config = GlobalConfig(
        local_asn=65000,
        router_id="10.0.0.2",
        rd_base=65000,
        rt_base=65000,
        neighbours=[
            Neighbor(
                address="172.31.100.11",
                remote_asn=65100,
                families=(AddressFamily.VPNV4,),
            )
        ],
    )
    return VPNv4RouteDriver(config=config, output_dir=tmp_path)


def test_driver_allocates_vrf(tmp_path: Path):
    driver = build_driver(tmp_path)

    tenant = driver.ensure_namespace("tenant-a")

    assert tenant.vrf.rd.startswith("65000:")
    assert tenant.vrf.import_rts == tenant.vrf.export_rts


def test_driver_advertises_prefix(tmp_path: Path):
    driver = build_driver(tmp_path)

    driver.advertise_prefixes("tenant-a", ["10.244.0.0/24"])

    rendered = driver.get_rendered_config()
    assert rendered is not None
    assert "network 10.244.0.0/24" in rendered


def test_driver_withdraws_prefix(tmp_path: Path):
    driver = build_driver(tmp_path)

    driver.advertise_prefixes("tenant-a", ["10.244.0.0/24"])
    driver.withdraw_prefixes("tenant-a", ["10.244.0.0/24"])

    rendered = driver.get_rendered_config()
    assert rendered is not None
    assert "! no prefixes advertised yet" in rendered


def test_driver_synchronize_prefixes(tmp_path: Path):
    driver = build_driver(tmp_path)

    driver.synchronize_prefixes("tenant-a", ["10.244.0.0/24", "10.244.0.0/24"])

    first_render = driver.get_rendered_config()
    assert first_render is not None
    assert first_render.count("network 10.244.0.0/24") == 1

    driver.synchronize_prefixes("tenant-a", ["10.244.0.0/24"])

    second_render = driver.get_rendered_config()
    assert second_render == first_render

