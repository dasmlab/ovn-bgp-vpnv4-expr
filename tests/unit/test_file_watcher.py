import json
import time
from pathlib import Path
from threading import Event

from ovn_bgp_agent import DriverRegistry
from ovn_bgp_agent.events import NamespaceUpsert
from ovn_bgp_agent.drivers import build_vpnv4_adapter
from ovn_bgp_vpnv4.config import GlobalConfig, Neighbor
from ovn_bgp_vpnv4.driver import VPNv4RouteDriver
from vpnv4_agent.watchers.file import FileNamespaceWatcher


class RecordingAdapter:
    def __init__(self):
        self.events: list[NamespaceUpsert] = []

    def on_namespace_upsert(self, namespace: str, prefixes):
        self.events.append(NamespaceUpsert(namespace, list(prefixes)))

    def on_namespace_delete(self, namespace: str):
        pass


def build_registry(tmp_path: Path) -> DriverRegistry:
    global_cfg = GlobalConfig(
        local_asn=65000,
        router_id="10.0.0.2",
        rd_base=65000,
        rt_base=65000,
        neighbours=[Neighbor(address="192.0.2.1", remote_asn=65100)],
    )
    driver = VPNv4RouteDriver(global_cfg, tmp_path)
    registry = DriverRegistry()
    registry.register("vpnv4", build_vpnv4_adapter(driver))
    return registry


def test_file_watcher_publishes_updates(tmp_path: Path):
    tenants_file = tmp_path / "tenants.json"
    tenants_file.write_text(
        json.dumps(
            {
                "tenants": [
                    {
                        "namespace": "demo",
                        "prefixes": ["10.1.0.0/24"],
                    }
                ]
            }
        )
    )

    registry = build_registry(tmp_path)

    stop_event = Event()
    watcher = FileNamespaceWatcher(
        registry=registry,
        path=tenants_file,
        interval=0.1,
        stop_event=stop_event,
    )

    # Replace registry driver with recording adapter for assertions
    recorder = RecordingAdapter()
    registry._drivers["vpnv4"] = recorder  # type: ignore[attr-defined]

    watcher.poll()
    assert recorder.events == [NamespaceUpsert("demo", ["10.1.0.0/24"])]

    recorder.events.clear()
    tenants_file.write_text(
        json.dumps(
            {
                "tenants": [
                    {
                        "namespace": "demo",
                        "prefixes": ["10.1.0.0/24", "10.2.0.0/24"],
                    }
                ]
            }
        )
    )

    watcher.poll()
    assert recorder.events == [NamespaceUpsert("demo", ["10.1.0.0/24", "10.2.0.0/24"])]

    stop_event.set()


