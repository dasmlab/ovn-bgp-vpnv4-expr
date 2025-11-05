# Tests Overview

## Structure (Proposed)

- `unit/`: Python/Go unit tests (RD/RT allocator, config rendering).
- `integration/`: docker-compose backed tests driving FRR ↔ simulator.
- `system/`: kind-based end-to-end scenarios (optional in CI, default for manual runs).

## Entry Points

- `make test`: executes unit + integration tiers locally.
- `pytest -m unit` / `go test ./...`: for targeted language-specific runs.
- `scripts/tests/run-system.sh` (future): orchestrates kind-based scenario.

## Fixtures & Tooling

- Use `pytest` fixtures to spin up ephemeral GoBGP instances via REST API.
- Export golden FRR configs into `tests/golden/` for regression checks.
- Capture BGP message traces with `scapy` to assert attribute correctness.

## TODOs

- Create simulator client library (Python/Go) to abstract REST operations.
- Define tagging strategy (unit/integration/system) for selective execution.
- Integrate coverage reporting into CI once test scaffolding lands.

