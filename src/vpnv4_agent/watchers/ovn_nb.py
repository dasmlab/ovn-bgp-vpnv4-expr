"""OVN Northbound poller that aggregates prefixes per namespace."""

from __future__ import annotations

import logging
from collections import defaultdict
from threading import Event, Thread
from typing import Dict, Iterable, Mapping

from ovn_bgp_agent import config as agent_config
from ovn_bgp_agent.drivers.openstack.utils import ovn as ovn_utils
from ovn_bgp_agent.drivers.openstack.utils import port as port_utils
from ovn_bgp_agent import exceptions as agent_exceptions
from ovn_bgp_agent.constants import OVN_CIDRS_EXT_ID_KEY

from ovn_bgp_agent.events import NamespaceDelete, NamespaceUpsert

from vpnv4_agent.watchers.utils import namespace_from_external_ids, normalize_prefix

LOG = logging.getLogger(__name__)


class NamespaceAggregator:
    def __init__(self, registry):
        self._registry = registry
        self._current: Dict[str, set[str]] = {}

    def update(self, mapping: Mapping[str, Iterable[str]]) -> None:
        desired = {ns: set(normalize_prefix(p) for p in prefixes)
                   for ns, prefixes in mapping.items() if prefixes}

        LOG.debug("OVN watcher computed desired namespaces: %s", desired)

        for namespace, prefixes in desired.items():
            if self._current.get(namespace) != prefixes:
                self._current[namespace] = prefixes
                self._registry.handle(NamespaceUpsert(namespace, sorted(prefixes)))

        for namespace in list(self._current.keys()):
            if namespace not in desired:
                del self._current[namespace]
                self._registry.handle(NamespaceDelete(namespace))


class OVNNamespaceWatcher(Thread):
    """Poll OVN NB DB and aggregate prefixes per namespace."""

    def __init__(
        self,
        registry,
        *,
        nb_connection: str,
        interval: float,
        stop_event: Event,
    ) -> None:
        super().__init__(daemon=True)
        self._registry = registry
        self._nb_connection = nb_connection
        self._interval = interval
        self._stop = stop_event
        self._aggregator = NamespaceAggregator(registry)

    def run(self) -> None:
        agent_config.register_opts()
        agent_config.init([])
        agent_config.CONF.set_override('ovn_nb_connection', self._nb_connection, group='ovn')

        LOG.info("Starting OVN namespace watcher (connection=%s, interval=%ss)", self._nb_connection, self._interval)

        nb_idl = ovn_utils.OvnNbIdl(
            self._nb_connection,
            tables=['Logical_Switch_Port'],
            events=None,
            leader_only=True,
        ).start()

        try:
            while not self._stop.is_set():
                try:
                    mapping = self._collect_prefixes(nb_idl)
                    LOG.debug("OVN poll found %d namespaces with prefixes", len(mapping))
                    self._aggregator.update(mapping)
                except Exception:  # pragma: no cover - defensive logging
                    LOG.exception("Failed to refresh OVN namespace state")
                self._stop.wait(self._interval)
        finally:
            LOG.info("Stopping OVN namespace watcher")
            nb_idl.ovsdb_connection.stop()

    def _collect_prefixes(self, nb_idl) -> Dict[str, set[str]]:
        rows = nb_idl.db_list_rows('Logical_Switch_Port').execute(check_error=True)
        mapping: Dict[str, set[str]] = defaultdict(set)
        for row in rows:
            namespace = namespace_from_external_ids(row.external_ids)
            if not namespace:
                continue
            try:
                ips = port_utils.get_ips_from_lsp(row)
            except agent_exceptions.IpAddressNotFound:
                continue
            for ip in ips:
                mapping[namespace].add(ip)
            cidrs = row.external_ids.get(OVN_CIDRS_EXT_ID_KEY, "").split()
            for cidr in cidrs:
                if cidr:
                    mapping[namespace].add(cidr)
        return mapping


def create_ovn_watcher(registry, options: Mapping[str, str], stop_event: Event, default_interval: float):
    nb_connection = options.get('connection') or options.get('ovn_nb_connection')
    if not nb_connection:
        raise ValueError("OVN watcher requires 'connection' (OVN NB connection URI)")
    interval = float(options.get('interval', default_interval))
    return OVNNamespaceWatcher(
        registry,
        nb_connection=nb_connection,
        interval=interval,
        stop_event=stop_event,
    )


