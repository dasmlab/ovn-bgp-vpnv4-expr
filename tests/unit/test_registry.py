from pathlib import Path

from ovn_bgp_agent import DriverRegistry, NamespaceDelete, NamespaceUpsert
from ovn_bgp_agent.drivers import build_vpnv4_adapter
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


def test_registry_dispatches_events(tmp_path: Path):
    driver = build_driver(tmp_path)
    registry = DriverRegistry()
    registry.register("vpnv4", build_vpnv4_adapter(driver))

    registry.handle(NamespaceUpsert(namespace="demo", prefixes=["10.200.0.0/24"]))

    config = driver.get_rendered_config()
    assert config is not None
    assert "network 10.200.0.0/24" in config

    registry.handle(NamespaceUpsert(namespace="demo", prefixes=[]))
    config = driver.get_rendered_config()
    assert config is not None
    assert "! no prefixes advertised yet" in config

    registry.handle(NamespaceDelete(namespace="demo"))
    assert all(tenant.namespace != "demo" for tenant in driver.list_tenants())


def test_registry_rejects_duplicate_registration(tmp_path: Path):
    driver = build_driver(tmp_path)
    registry = DriverRegistry()
    adapter = build_vpnv4_adapter(driver)

    registry.register("vpnv4", adapter)

    try:
        registry.register("vpnv4", adapter)
    except ValueError:
        pass
    else:
        raise AssertionError("duplicate registration did not raise ValueError")


