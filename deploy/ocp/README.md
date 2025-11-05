# OpenShift Deployment Notes (vpnv4 Driver)

This directory captures the artefacts and operator notes required to deploy the
vpnv4 driver on an OpenShift cluster once it is wired into the upstream
`ovn-bgp-agent`.

## 1. Prerequisites

1. **Custom agent image** – build/publish an image that contains the new
   vpnv4 driver modules (e.g. `quay.io/<org>/ovn-bgp-agent:vpnv4`).
2. **Kernel modules** – every node running the agent must load
   `mpls_router` and `mpls_iptunnel`.  See the MachineConfig snippet below.
3. **FortiGate reachability** – ensure the OpenShift nodes can reach the
   FortiGate loopback or peering IPs used for the MP-BGP sessions.

## 2. MachineConfig snippet (MPLS modules)

```yaml
apiVersion: machineconfiguration.openshift.io/v1
kind: MachineConfig
metadata:
  name: 99-vpnv4-mpls-modules
  labels:
    machineconfiguration.openshift.io/role: worker
spec:
  config:
    ignition:
      version: 3.2.0
    storage:
      files:
        - path: /etc/modprobe.d/vpnv4.conf
          mode: 0644
          contents:
            source: data:text/plain;base64,bXBsc19yb3V0ZXIAbXBsc19pcHR1bm5lbAo=
    systemd:
      units:
        - name: vpnv4-mpls.service
          enabled: true
          contents: |
            [Unit]
            Description=Load MPLS modules for vpnv4
            After=network.target

            [Service]
            Type=oneshot
            ExecStart=/usr/sbin/modprobe mpls_router
            ExecStart=/usr/sbin/modprobe mpls_iptunnel

            [Install]
            WantedBy=multi-user.target
```

> Apply a copy of this MachineConfig to each relevant pool (e.g. `worker`,
> `worker-rt`). Reboot nodes or wait for the MachineConfig Operator to drain
> and update them.

## 3. Agent configuration ConfigMap

`vpnv4-agent` expects a YAML configuration file (default path
`/etc/ovn-bgp-agent/vpnv4.yaml`).  The sample ConfigMap below matches the
structure consumed by `vpnv4_agent.config.load_config`.

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: ovn-bgp-agent-config
  namespace: openshift-ovn-kubernetes
data:
  vpnv4.yaml: |
    driver:
      local_asn: 65000
      router_id: 10.255.0.2
      rd_base: 65000
      rt_base: 65000
      output_dir: /etc/frr
      include_globals: true
      maintain_empty_vrf: true
      neighbours:
        - address: 192.0.2.11
          remote_asn: 65101
        - address: 192.0.2.12
          remote_asn: 65102
        - address: 192.0.2.13
          remote_asn: 65103
    watchers:
      - type: ovn
        options:
          connection: unix:/var/run/ovn/ovnnb_db.sock
          interval: 5
    tenants.json: |
      {
        "tenants": [
          {"namespace": "demo", "prefixes": ["10.244.0.0/24"]}
        ]
      }
```

Mount the ConfigMap as a volume so the binary finds both `vpnv4.yaml` and the
`tenants.json` file watched by the file-based namespace watcher.  Automating the
tenants feed (e.g. via a controller) is a follow-up task.

When `watchers` includes an entry of `type: ovn`, the agent polls the OVN
Northbound DB directly and emits namespace events based on logical switch port
addresses. Provide a valid `options.connection` URI for your control-plane.

## 4. DaemonSet patch (driver wiring)

```yaml
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: ovn-bgp-agent
  namespace: openshift-ovn-kubernetes
spec:
  template:
    spec:
      containers:
        - name: ovn-bgp-agent
          image: ghcr.io/<org>/ovn-bgp-agent:vpnv4-dev
          env:
            - name: OVN_BGP_DRIVER
              value: vpnv4
            - name: OVN_BGP_CONFIG
              value: /etc/ovn-bgp-agent/vpnv4.yaml
          volumeMounts:
            - name: ovn-bgp-agent-config
              mountPath: /etc/ovn-bgp-agent
      volumes:
        - name: ovn-bgp-agent-config
          configMap:
            name: ovn-bgp-agent-config
```

> The real DaemonSet may include additional volumes (kubeconfig, host network,
> etc.).  Merge the snippet above with the existing manifest instead of
> replacing it entirely.

## 5. Validation checklist

1. Confirm pods are running: `oc get pods -n openshift-ovn-kubernetes -l app=ovn-bgp-agent`.
2. Inspect logs for the vpnv4 driver (`grep vpnv4`).
3. Verify MP-BGP sessions from each node to the FortiGate peers (use `vtysh` or
   the new lab validation script as a reference).
4. Ensure Linux VRFs contain the exported prefixes and any imported routes from
   the FortiGates.

Once the upstream integration lands, these manifests can be converted into
Helm/Ansible templates or folded into the official operator.

