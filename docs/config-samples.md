# Configuration Samples

Use these snippets as a starting point for automation templates. Replace placeholder values (`<...>`) with lab-specific data during rendering.

## 1. FRR `frr.conf`

```
frr version 8.x
frr defaults traditional
hostname frr-vpnv4-lab
service integrated-vtysh-config
!
router bgp <LOCAL_ASN>
 bgp router-id <ROUTER_ID>
 neighbor <SIMULATOR_IP> remote-as <REMOTE_ASN>
 neighbor <SIMULATOR_IP> description FortiGate-sim
 !
 address-family vpnv4
  neighbor <SIMULATOR_IP> activate
  neighbor <SIMULATOR_IP> send-community both
 exit-address-family
!
router bgp <LOCAL_ASN> vrf <TENANT_NAME>
 rd <LOCAL_ASN>:<TENANT_ID>
 route-target import <LOCAL_ASN>:<TENANT_RT>
 route-target export <LOCAL_ASN>:<TENANT_RT>
 !
 address-family ipv4 unicast
  redistribute kernel
 exit-address-family
!
line vty
!
```

## 2. GoBGP Simulator Config (`gobgp.conf`)

```
[global.config]
  as = <REMOTE_ASN>
  router-id = "<SIMULATOR_ROUTER_ID>"

[[neighbors]]
  [neighbors.config]
    neighbor-address = "<FRR_IP>"
    peer-as = <LOCAL_ASN>
  [neighbors.afi-safis]
    [[neighbors.afi-safis.config]]
      afi-safi-name = "l3vpn-ipv4-unicast"
  [neighbors.transport.config]
    remote-port = 179

[[policy-definitions]]
  name = "accept-vpnv4"
  [[policy-definitions.statements]]
    [policy-definitions.statements.conditions.match-afi-safi]
      afi-safi-name = "l3vpn-ipv4-unicast"
    [policy-definitions.statements.actions.route-disposition]
      accept-route = true

[defined-sets.ext-community-sets]
  [[defined-sets.ext-community-sets.config]]
    ext-community-set-name = "allowed-rt"
    member = ["target:<LOCAL_ASN>:<TENANT_RT>"]

[[policy-definitions]]
  name = "filter-by-rt"
  [[policy-definitions.statements]]
    [policy-definitions.statements.conditions.match-ext-community-set]
      ext-community-set = "allowed-rt"
    [policy-definitions.statements.actions.route-disposition]
      accept-route = true

[policy-assignment.import-policy]
  apply-policy-list = ["filter-by-rt"]
```

## 3. FortiGate CLI Reference (for hardware validation)

```
config router bgp
  set as <REMOTE_ASN>
  config neighbor
    edit "<FRR_IP>"
      set remote-as <LOCAL_ASN>
      set capability vpnv4 enable
      set soft-reconfiguration enable
    next
  end
  config vrf
    edit <VRF_ID>
      set rd <LOCAL_ASN>:<TENANT_ID>
      set route-target-import <LOCAL_ASN>:<TENANT_RT>
      set route-target-export <LOCAL_ASN>:<TENANT_RT>
    next
  end
end
```

## 4. OVN-BGP-Agent Configuration Snippet (pseudo YAML)

```
bgp:
  mode: vpnv4
  local-asn: <LOCAL_ASN>
  rd-base: <LOCAL_ASN>
  rt-base: <LOCAL_ASN>
  neighbors:
    - address: <SIMULATOR_IP>
      remote-asn: <REMOTE_ASN>
      afi-safis:
        - vpnv4
    - address: <OPTIONAL_BACKUP>
      remote-asn: <REMOTE_ASN>

tenants:
  - namespace: tenant-a
    rd-id: 100
    rt-id: 100
  - namespace: tenant-b
    rd-id: 101
    rt-id: 101
```

> Replace these pseudo structures with actual agent configuration format once the driver interface is finalized.

