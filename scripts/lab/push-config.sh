#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd -- "${SCRIPT_DIR}/../.." && pwd)

CONFIG_ROOT="${REPO_ROOT}/deploy/frr"

if [[ ! -d "${CONFIG_ROOT}" ]]; then
  echo "[push-config] WARN: ${CONFIG_ROOT} does not exist yet; skipping push." >&2
  exit 0
fi

echo "[push-config] Rendering and pushing FRR configuration snippets..."

# TODO: render templates (ytt/jinja2) into ${CONFIG_ROOT}/rendered
# TODO: copy configs into FRR containers (docker cp + vtysh reload)

echo "[push-config] Completed placeholder workflow." 

