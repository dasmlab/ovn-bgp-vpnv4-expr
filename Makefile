.PHONY: deps lab-up lab-down vpnv4-config vpnv4-apply test observe fmt clean

REPO_ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
AGENT_IMAGE ?= ghcr.io/dasmlab/ovn-bgp-agent:vpnv4-dev

deps:
	@echo "[make deps] Installing lab dependencies (placeholder)."
	@echo "# TODO: implement hack/install-tools.sh"

lab-up:
	@echo "[make lab-up] Bringing up lab via scripts/lab/lab-up.sh"
	@"$(REPO_ROOT)/scripts/lab/lab-up.sh"

lab-down:
	@echo "[make lab-down] Tearing down lab via scripts/lab/lab-down.sh"
	@"$(REPO_ROOT)/scripts/lab/lab-down.sh"

vpnv4-config:
	@echo "[make vpnv4-config] Rendering vpnv4 FRR configuration"
	@python3 "$(REPO_ROOT)/scripts/vpnv4/render.py" --tenants "$(REPO_ROOT)/deploy/vpnv4/tenants.json" --output-dir "$(REPO_ROOT)/deploy/frr"

vpnv4-apply: vpnv4-config
	@echo "[make vpnv4-apply] Reloading FRR configuration"
	@docker exec frr-vpnv4 vtysh -f /etc/frr/frr.merged.conf
	@python3 "$(REPO_ROOT)/scripts/vpnv4/setup_vrfs.py" --tenants "$(REPO_ROOT)/deploy/vpnv4/tenants.json" --container frr-vpnv4

agent-image:
	@echo "[make agent-image] Building vpnv4 agent image ($(AGENT_IMAGE))"
	@docker build -f "$(REPO_ROOT)/images/agent/Dockerfile" -t "$(AGENT_IMAGE)" "$(REPO_ROOT)"

agent-push:
	@echo "[make agent-push] Pushing vpnv4 agent image ($(AGENT_IMAGE))"
	@docker push "$(AGENT_IMAGE)"

test:
	@echo "[make test] Running unit/integration tests (placeholder)."
	@echo "# TODO: add pytest/go test commands"

observe:
	@echo "[make observe] Collecting diagnostics (placeholder)."
	@echo "# TODO: implement scripts/lab/collect-logs.sh"

fmt:
	@echo "[make fmt] Formatting configs/code (placeholder)."
	@echo "# TODO: run gofmt / black / shellcheck"

clean: lab-down
	@echo "[make clean] Cleanup complete."

