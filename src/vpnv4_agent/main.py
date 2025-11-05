"""Entry point for the standalone vpnv4 agent."""

from __future__ import annotations

import argparse
import logging
import signal
import sys
from pathlib import Path
from threading import Event

from ovn_bgp_agent import DriverRegistry
from ovn_bgp_agent.drivers import build_vpnv4_adapter
from ovn_bgp_vpnv4.driver import VPNv4RouteDriver

from .config import load_config
from .watchers import FileNamespaceWatcher

LOG = logging.getLogger(__name__)


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the vpnv4 agent")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("/etc/ovn-bgp-agent/vpnv4.yaml"),
        help="Path to the agent configuration file",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )

    args = parser.parse_args(argv)
    _setup_logging(args.verbose)

    config = load_config(args.config)

    driver = VPNv4RouteDriver(
        config.driver.to_global_config(),
        output_dir=config.driver.output_dir,
        include_globals=config.driver.include_globals,
    )

    registry = DriverRegistry()
    registry.register(
        "vpnv4",
        build_vpnv4_adapter(
            driver, maintain_empty_vrf=config.driver.maintain_empty_vrf
        ),
    )

    stop_event = Event()

    watchers = []
    for watcher_cfg in config.watchers:
        if watcher_cfg.type == "file":
            watcher = FileNamespaceWatcher(
                registry=registry,
                path=watcher_cfg.path,
                interval=watcher_cfg.interval,
                stop_event=stop_event,
            )
        else:
            raise ValueError(f"unsupported watcher type '{watcher_cfg.type}'")
        # Perform an initial poll so we react immediately
        try:
            watcher.poll()
        except Exception:  # pragma: no cover - logged inside watcher
            LOG.exception("initial poll failed for watcher %s", watcher_cfg.path)
        watcher.start()
        watchers.append(watcher)

    if not watchers:
        LOG.warning("no watchers configured; agent will idle")

    def _shutdown(signum, frame):  # pragma: no cover - signal handler
        LOG.info("received signal %s, shutting down", signum)
        stop_event.set()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        while not stop_event.is_set():
            stop_event.wait(1.0)
    except KeyboardInterrupt:  # pragma: no cover - fallback if signal not set
        stop_event.set()

    for watcher in watchers:
        watcher.join()

    LOG.info("vpnv4 agent stopped")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())


