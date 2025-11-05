from pathlib import Path

import pytest

from vpnv4_agent.config import load_config


def test_load_config(tmp_path: Path):
    config_path = tmp_path / "vpnv4.yaml"
    config_path.write_text(
        """
driver:
  local_asn: 65000
  router_id: 10.255.0.2
  rd_base: 65000
  rt_base: 65000
  output_dir: /var/lib/frr
  include_globals: true
  maintain_empty_vrf: false
  neighbours:
    - address: 192.0.2.1
      remote_asn: 65100
watchers:
  - type: file
    path: /etc/ovn-bgp-agent/tenants.json
    interval: 2
  - type: ovn
    options:
      connection: unix:/var/run/ovn/ovnnb_db.sock
      interval: 3
"""
    )

    cfg = load_config(config_path)

    assert cfg.driver.local_asn == 65000
    assert cfg.driver.router_id == "10.255.0.2"
    assert cfg.driver.include_globals is True
    assert cfg.driver.maintain_empty_vrf is False
    assert cfg.driver.output_dir == Path("/var/lib/frr")
    assert len(cfg.driver.neighbours) == 1
    neigh = cfg.driver.neighbours[0]
    assert neigh.address == "192.0.2.1"
    assert neigh.remote_asn == 65100
    assert len(cfg.watchers) == 2
    watcher = cfg.watchers[0]
    assert watcher.type == "file"
    assert watcher.path == Path("/etc/ovn-bgp-agent/tenants.json")
    assert watcher.interval == pytest.approx(2.0)
    assert watcher.options == {}

    ovn_watcher = cfg.watchers[1]
    assert ovn_watcher.type == "ovn"
    assert ovn_watcher.interval == pytest.approx(5.0)
    assert ovn_watcher.options["connection"] == "unix:/var/run/ovn/ovnnb_db.sock"
    assert ovn_watcher.options["interval"] == 3


