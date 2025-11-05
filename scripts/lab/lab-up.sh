#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd -- "${SCRIPT_DIR}/../.." && pwd)

ENV_FILE="${SCRIPT_DIR}/.env"
if [[ -f "${ENV_FILE}" ]]; then
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
else
  echo "[lab-up] WARN: ${ENV_FILE} not found; using default environment values" >&2
fi

export PATH="${REPO_ROOT}/bin:${PATH}"

CLUSTER_NAME=${CLUSTER_NAME:-ovn-bgp-lab}
KUBECONFIG_PATH=${KUBECONFIG:-${REPO_ROOT}/artifacts/kubeconfig}
KIND_CONFIG=${KIND_CONFIG:-${REPO_ROOT}/deploy/kind/cluster-config.yaml}
COMPOSE_FILE=${COMPOSE_FILE:-${REPO_ROOT}/deploy/compose/docker-compose.yaml}
OVN_DIST_DIR=${OVN_DIST_DIR:-${REPO_ROOT}/externals/ovn-kubernetes/dist}
OVN_IMAGE=${OVN_IMAGE:-ghcr.io/dasmlab/ovn-daemonset-fedora:dev}
OVNKUBE_IMAGE=${OVNKUBE_IMAGE:-${OVN_IMAGE}}
OVN_RENDER_DIR=${OVN_RENDER_DIR:-${REPO_ROOT}/deploy/ovn/rendered}
ARTIFACT_DIR=$(dirname "${KUBECONFIG_PATH}")

echo "[lab-up] Starting OVN-BGP vpnv4 lab..."

require_cmd() {
  local cmd=$1
  if ! command -v "${cmd}" >/dev/null 2>&1; then
    echo "[lab-up] ERROR: required command '${cmd}' not found in PATH" >&2
    exit 1
  fi
}

require_cmd kind
require_cmd kubectl
require_cmd docker
require_cmd curl
require_cmd jq

if ! docker compose version >/dev/null 2>&1; then
  echo "[lab-up] ERROR: docker compose plugin not available" >&2
  exit 1
fi

mkdir -p "${ARTIFACT_DIR}"

load_mpls_modules() {
  local modules=(mpls_router mpls_iptunnel)
  if ! command -v modprobe >/dev/null 2>&1; then
    echo "[lab-up] WARN: modprobe not available; skipping MPLS module load" >&2
    return 0
  fi

  for mod in "${modules[@]}"; do
    if lsmod | grep -q "^${mod} " ; then
      echo "[lab-up] ${mod} already loaded"
      continue
    fi

    if sudo -n modprobe "${mod}" 2>/dev/null; then
      echo "[lab-up] Loaded ${mod} via sudo"
      continue
    fi

    if [[ -n "${LAB_SUDO_PASS:-}" ]]; then
      if echo "${LAB_SUDO_PASS}" | sudo -S modprobe "${mod}" >/dev/null 2>&1; then
        echo "[lab-up] Loaded ${mod} via sudo -S"
        continue
      fi
    fi

    if modprobe "${mod}" 2>/dev/null; then
      echo "[lab-up] Loaded ${mod}"
    else
      echo "[lab-up] WARN: failed to load ${mod}; vpnv4 dataplane tests may be limited" >&2
    fi
  done
}

discover_control_plane_ip() {
  local ip
  if ip=$(docker inspect "${CLUSTER_NAME}-control-plane" --format '{{ .NetworkSettings.Networks.kind.IPAddress }}' 2>/dev/null); then
    if [[ -n "${ip}" && "${ip}" != "<no value>" ]]; then
      echo "${ip}"
      return 0
    fi
  fi

  ip=$(kubectl --kubeconfig "${KUBECONFIG_PATH}" get node "${CLUSTER_NAME}-control-plane" -o jsonpath='{.status.addresses[?(@.type=="InternalIP")].address}' 2>/dev/null || true)
  if [[ -n "${ip}" ]]; then
    echo "${ip}"
    return 0
  fi

  echo ""
  return 1
}

build_ovn_db_endpoints() {
  local port=$1
  kubectl --kubeconfig "${KUBECONFIG_PATH}" get pod -n ovn-kubernetes -l name=ovnkube-db -o jsonpath="{range .items[*]}tcp:{.status.podIP}:${port} {end}" |
    tr -s ' ' '\n' | grep -v '^$' | paste -sd, -
}

patch_ovn_db_env() {
  local nb_endpoints=$1
  local sb_endpoints=$2
  local targets=("deployment/ovnkube-master" "deployment/ovnkube-control-plane" "daemonset/ovnkube-node" "daemonset/ovnkube-identity")

  for target in "${targets[@]}"; do
    echo "[lab-up] patching ${target} with OVN db endpoints"
    kubectl --kubeconfig "${KUBECONFIG_PATH}" set env -n ovn-kubernetes "${target}" \
      OVN_NORTH="${nb_endpoints}" \
      OVN_SOUTH="${sb_endpoints}" \
      OVN_NBDB="${nb_endpoints}" \
      OVN_SBDB="${sb_endpoints}" >/dev/null
  done
}

recycle_ovn_pods() {
  local selector=$1
  echo "[lab-up] recycling OVN pods (${selector})"
  kubectl --kubeconfig "${KUBECONFIG_PATH}" delete pod -n ovn-kubernetes -l "${selector}" --ignore-not-found >/dev/null || true
}

wait_for_selector() {
  local selector=$1
  local namespace=$2
  local timeout=${3:-120}
  local start=$(date +%s)
  while true; do
    if kubectl --kubeconfig "${KUBECONFIG_PATH}" get pods -n "${namespace}" -l "${selector}" --no-headers >/dev/null 2>&1; then
      local count
      count=$(kubectl --kubeconfig "${KUBECONFIG_PATH}" get pods -n "${namespace}" -l "${selector}" --no-headers 2>/dev/null | wc -l)
      if [[ ${count} -gt 0 ]]; then
        break
      fi
    fi
    if (( $(date +%s) - start > timeout )); then
      echo "[lab-up] WARN: selector '${selector}' in namespace '${namespace}' not populated after ${timeout}s" >&2
      break
    fi
    sleep 3
  done
}

echo "[lab-up] step 0/4: ensuring MPLS kernel modules are present"
load_mpls_modules

echo "[lab-up] step 1/4: creating kind cluster"
if kind get clusters | grep -q "^${CLUSTER_NAME}$"; then
  echo "[lab-up] kind cluster '${CLUSTER_NAME}' already exists"
else
  kind create cluster --name "${CLUSTER_NAME}" --config "${KIND_CONFIG}"
fi

export KUBECONFIG="${KUBECONFIG_PATH}"
kind get kubeconfig --name "${CLUSTER_NAME}" > "${KUBECONFIG_PATH}"

CONTROL_PLANE_IP=$(discover_control_plane_ip || true)
if [[ -z "${CONTROL_PLANE_IP}" ]]; then
  echo "[lab-up] ERROR: unable to determine kind control plane IP" >&2
  exit 1
fi
API_SERVER_ENDPOINT="https://${CONTROL_PLANE_IP}:6443"

echo "[lab-up] step 2/4: waiting for control plane"
kubectl --kubeconfig "${KUBECONFIG_PATH}" wait nodes --for=condition=Ready --all --timeout=180s || true

echo "[lab-up] step 2a/4: rendering OVN manifests (image=${OVN_IMAGE})"
mkdir -p "${OVN_RENDER_DIR}"
rm -f "${OVN_RENDER_DIR}"/*.yaml
(
  cd "${OVN_DIST_DIR}/images"
  OVNKUBE_IMAGE="${OVNKUBE_IMAGE}" ./daemonset.sh \
    --image="${OVN_IMAGE}" \
    --net-cidr=10.244.0.0/16 \
    --svc-cidr=10.96.0.0/16 \
    --gateway-mode=shared \
    --output-directory="${OVN_RENDER_DIR}"
)

echo "[lab-up] step 2b/4: applying OVN base resources"
kubectl --kubeconfig "${KUBECONFIG_PATH}" apply -f <(sed "s#k8s_apiserver: .*#k8s_apiserver: ${API_SERVER_ENDPOINT}#" "${OVN_RENDER_DIR}/ovn-setup.yaml")

echo "[lab-up] step 2c/4: creating GHCR pull secret"
GHCR_AUTH=$(jq -r '.auths["ghcr.io"].auth // empty' < "${HOME}/.docker/config.json" || echo "")
if [[ -z "${GHCR_AUTH}" ]]; then
  echo "[lab-up] ERROR: ghcr.io credentials not found in ~/.docker/config.json" >&2
  exit 1
fi
DECODED_AUTH=$(echo "${GHCR_AUTH}" | base64 -d)
GHCR_USER=${DECODED_AUTH%%:*}
GHCR_TOKEN=${DECODED_AUTH#*:}
kubectl --kubeconfig "${KUBECONFIG_PATH}" -n ovn-kubernetes create secret docker-registry registry-credentials \
  --docker-server=ghcr.io \
  --docker-username="${GHCR_USER}" \
  --docker-password="${GHCR_TOKEN}" \
  --dry-run=client -o yaml | kubectl --kubeconfig "${KUBECONFIG_PATH}" apply -f -

echo "[lab-up] step 2d/4: applying OVN RBAC and service accounts"
for file in "${OVN_RENDER_DIR}"/rbac-ovnkube-*.yaml; do
  kubectl --kubeconfig "${KUBECONFIG_PATH}" apply -f "${file}"
done

echo "[lab-up] step 2e/4: patching service accounts with registry pull secret"
for sa in default ovnkube-db ovnkube-master ovnkube-node ovnkube-identity ovnkube-cluster-manager; do
  if kubectl --kubeconfig "${KUBECONFIG_PATH}" get serviceaccount "${sa}" -n ovn-kubernetes >/dev/null 2>&1; then
    kubectl --kubeconfig "${KUBECONFIG_PATH}" patch serviceaccount "${sa}" -n ovn-kubernetes \
      --type merge -p '{"imagePullSecrets":[{"name":"registry-credentials"}]}'
  fi
done

echo "[lab-up] step 2f/4: applying OVN control plane components"
kubectl --kubeconfig "${KUBECONFIG_PATH}" delete deployment ovnkube-db -n ovn-kubernetes --ignore-not-found >/dev/null 2>&1 || true
kubectl --kubeconfig "${KUBECONFIG_PATH}" apply -f "${OVN_RENDER_DIR}/ovnkube-db-raft.yaml"
kubectl --kubeconfig "${KUBECONFIG_PATH}" apply -f "${OVN_RENDER_DIR}/ovnkube-master.yaml"
kubectl --kubeconfig "${KUBECONFIG_PATH}" apply -f "${OVN_RENDER_DIR}/ovnkube-control-plane.yaml"
kubectl --kubeconfig "${KUBECONFIG_PATH}" apply -f "${OVN_RENDER_DIR}/ovnkube-node.yaml"
kubectl --kubeconfig "${KUBECONFIG_PATH}" apply -f "${OVN_RENDER_DIR}/ovnkube-identity.yaml"
kubectl --kubeconfig "${KUBECONFIG_PATH}" apply -f "${OVN_RENDER_DIR}/ovs-node.yaml"

echo "[lab-up] step 2g/4: labeling nodes for OVN"
for node in $(kubectl --kubeconfig "${KUBECONFIG_PATH}" get nodes -o name); do
  kubectl --kubeconfig "${KUBECONFIG_PATH}" label --overwrite "$node" k8s.ovn.org/ovnkube-db=true
done

echo "[lab-up] step 2h/4: waiting for OVN DB cluster"
wait_for_selector "app=ovnkube-db" ovn-kubernetes 180
kubectl --kubeconfig "${KUBECONFIG_PATH}" wait --for=condition=Ready pod -l app=ovnkube-db -n ovn-kubernetes --timeout=600s || true

NB_ENDPOINTS=$(build_ovn_db_endpoints 6641 || true)
SB_ENDPOINTS=$(build_ovn_db_endpoints 6642 || true)
if [[ -n "${NB_ENDPOINTS}" && -n "${SB_ENDPOINTS}" ]]; then
  echo "[lab-up] step 2i/4: configuring OVN components with DB endpoints"
  patch_ovn_db_env "${NB_ENDPOINTS}" "${SB_ENDPOINTS}"
  recycle_ovn_pods "name=ovnkube-master"
  recycle_ovn_pods "name=ovnkube-control-plane"
  recycle_ovn_pods "app=ovnkube-identity"
  recycle_ovn_pods "app=ovnkube-node"
else
  echo "[lab-up] WARN: unable to derive OVN DB endpoints; continuing without explicit overrides" >&2
fi

echo "[lab-up] step 2j/4: waiting for OVN control plane components"
wait_for_selector "app=ovnkube-node" ovn-kubernetes 180
kubectl --kubeconfig "${KUBECONFIG_PATH}" wait --for=condition=Ready pod -l app=ovnkube-node -n ovn-kubernetes --timeout=600s || true
wait_for_selector "app=ovnkube-master" ovn-kubernetes 180
kubectl --kubeconfig "${KUBECONFIG_PATH}" wait --for=condition=Ready pod -l app=ovnkube-master -n ovn-kubernetes --timeout=600s || true
wait_for_selector "name=ovnkube-control-plane" ovn-kubernetes 180
kubectl --kubeconfig "${KUBECONFIG_PATH}" wait --for=condition=Ready pod -l name=ovnkube-control-plane -n ovn-kubernetes --timeout=600s || true
wait_for_selector "app=ovnkube-identity" ovn-kubernetes 180
kubectl --kubeconfig "${KUBECONFIG_PATH}" wait --for=condition=Ready pod -l app=ovnkube-identity -n ovn-kubernetes --timeout=600s || true

echo "[lab-up] step 3/4: launching FRR + FortiGate simulator via docker compose"
docker compose -f "${COMPOSE_FILE}" up -d

echo "[lab-up] step 4/4: verifying vpnv4 control plane"
sleep 10
python3 "${SCRIPT_DIR}/validate_vpnv4.py"

echo "[lab-up] Lab bring-up routine completed."

