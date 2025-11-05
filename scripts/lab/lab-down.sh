#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd -- "${SCRIPT_DIR}/../.." && pwd)

ENV_FILE="${SCRIPT_DIR}/.env"
if [[ -f "${ENV_FILE}" ]]; then
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
fi

export PATH="${REPO_ROOT}/bin:${PATH}"

CLUSTER_NAME=${CLUSTER_NAME:-ovn-bgp-lab}
COMPOSE_FILE=${COMPOSE_FILE:-${REPO_ROOT}/deploy/compose/docker-compose.yaml}

echo "[lab-down] Destroying OVN-BGP vpnv4 lab resources..."

echo "[lab-down] step 1/3: shutting down docker-compose stack"
if docker compose -f "${COMPOSE_FILE}" ps >/dev/null 2>&1; then
  docker compose -f "${COMPOSE_FILE}" down --remove-orphans
else
  echo "[lab-down] docker compose stack already absent"
fi

echo "[lab-down] step 2/3: deleting kind cluster"
if kind get clusters | grep -q "^${CLUSTER_NAME}$"; then
  kind delete cluster --name "${CLUSTER_NAME}"
else
  echo "[lab-down] kind cluster '${CLUSTER_NAME}' already removed"
fi

echo "[lab-down] step 3/3: pruning leftover networks if LAB_KIND_NETWORK is set"
if [[ -n "${LAB_KIND_NETWORK:-}" ]]; then
  if docker network inspect "${LAB_KIND_NETWORK}" >/dev/null 2>&1; then
    docker network rm "${LAB_KIND_NETWORK}"
  fi
fi

echo "[lab-down] Lab teardown routine completed."

