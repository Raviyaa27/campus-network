# Design Document 1 — VLAN and IP Addressing Plan

EE8203 Campus Network — Faculty of Engineering, University of Ruhuna
Version 0.1

## 1. Address space

Private address space `10.0.0.0/8` is used throughout. Three distinct ranges are
allocated so that the purpose of any address is obvious from its prefix:

| Range | Purpose |
|-------|---------|
| `10.10.0.0/16` | Department user and server VLANs |
| `10.99.99.0/24` | Out-of-band management VLAN (VLAN 99) |
| `10.255.255.0/24` | Point-to-point routed links between L3 devices |
| `10.99.0.0/24` | Router management loopbacks |
| `192.168.25.0/24` | Simulated internet (outside NAT), provided by the GNS3 NAT node |

## 2. VLAN allocation

| VLAN | Name | Department | Subnet | Gateway (SVI on SW-CORE) | Purpose |
|------|------|-----------|--------|--------------------------|---------|
| 10 | VLAN_DEIE | DEIE | 10.10.10.0/24 | 10.10.10.1 (HSRP VIP) | Engineering workstations |
| 20 | VLAN_DCEE | DCEE | 10.10.20.0/24 | 10.10.20.1 (HSRP VIP) | Civil/Environmental hosts |
| 30 | VLAN_DMME | DMME | 10.10.30.0/24 | 10.10.30.1 (HSRP VIP) | Mechanical/Manufacturing hosts |
| 40 | VLAN_DIS | DIS | 10.10.40.0/24 | 10.10.40.1 (HSRP VIP) | Faculty IT hub / server farm |
| 99 | MGMT | All | 10.99.99.0/24 | 10.99.99.1 (HSRP VIP) | Device management, SSH only |
| 100 | NATIVE | Trunks | none | none | Native (untagged) VLAN on all trunks |

VLAN 100 carries no IP addressing. It is configured as the native VLAN on every
trunk so that no user traffic is ever carried untagged.

### 2.1 HSRP gateway addressing

The core is a redundant pair, SW-CORE-1 and SW-CORE-2. Each holds a real SVI in
every VLAN, and HSRP presents a single virtual gateway address to the hosts. Hosts
and DHCP scopes always point at the `.1` virtual address and are unaffected by a
core failover.

| VLAN | SW-CORE-1 SVI | SW-CORE-2 SVI | HSRP VIP | HSRP group | Active |
|------|---------------|---------------|----------|------------|--------|
| 10 | 10.10.10.2 | 10.10.10.3 | 10.10.10.1 | 10 | SW-CORE-1 |
| 20 | 10.10.20.2 | 10.10.20.3 | 10.10.20.1 | 20 | SW-CORE-1 |
| 30 | 10.10.30.2 | 10.10.30.3 | 10.10.30.1 | 30 | SW-CORE-2 |
| 40 | 10.10.40.2 | 10.10.40.3 | 10.10.40.1 | 40 | SW-CORE-2 |
| 99 | 10.99.99.2 | 10.99.99.3 | 10.99.99.1 | 99 | SW-CORE-1 |

Priorities: the designated active switch uses priority 110, the standby uses the
default 100, and `preempt` is enabled on both. VLANs 10, 20 and 99 are active on
SW-CORE-1 while VLANs 30 and 40 are active on SW-CORE-2, so that both cores carry
traffic in normal operation rather than leaving one idle. Each core remains the
standby for the other's VLANs, so a single failure moves all gateways to the
survivor.

Spanning tree root priorities are aligned with HSRP so that the L2 forwarding path
matches the L3 gateway: SW-CORE-1 is configured as STP root for VLANs 10, 20 and
99, and SW-CORE-2 as root for VLANs 30 and 40, with the peer as secondary root in
each case.

## 3. Point-to-point routed links

All inter-router and router-to-core-switch links use /30 subnets to conserve
address space and keep OSPF adjacencies explicit.

| Link | Subnet | Device A | IP A | Device B | IP B |
|------|--------|----------|------|----------|------|
| R-EDGE ↔ Internet | 192.168.25.0/24 | R-EDGE Gi0/0 | 192.168.25.10/24 | NAT node (gw) | 192.168.25.2 |
| R-EDGE ↔ R-CORE | 10.255.255.0/30 | R-EDGE Gi0/1 | 10.255.255.1 | R-CORE Gi0/1 | 10.255.255.2 |
| R-CORE ↔ SW-CORE-1 | 10.255.255.4/30 | R-CORE Gi0/2 | 10.255.255.5 | SW-CORE-1 Gi0/0 | 10.255.255.6 |
| R-CORE ↔ SW-CORE-2 | 10.255.255.8/30 | R-CORE Gi0/3 | 10.255.255.9 | SW-CORE-2 Gi0/0 | 10.255.255.10 |

R-CORE is dual-homed to both core switches so that the loss of one core switch or
one uplink does not isolate the campus from the edge. OSPF equal-cost multipath
load-shares across the two links in normal operation.

The SW-CORE-1 ↔ SW-CORE-2 peer link is an 802.1Q trunk carrying all VLANs, not a
routed link. It exists so that HSRP hello packets and any VLAN traffic homed on
the non-active core can cross between the pair.

## 4. Management addressing (VLAN 99)

Layer-3 switches are managed on their VLAN 99 SVI. Routers are not members of
VLAN 99, so they are managed on a loopback interface advertised into OSPF.

| Device | Management IP | Interface |
|--------|---------------|-----------|
| SW-CORE-1 | 10.99.99.2/24 | SVI VLAN 99 |
| SW-CORE-2 | 10.99.99.3/24 | SVI VLAN 99 |
| SW-D-DEIE | 10.99.99.11/24 | SVI VLAN 99 |
| SW-D-DCEE | 10.99.99.12/24 | SVI VLAN 99 |
| SW-D-DMME | 10.99.99.13/24 | SVI VLAN 99 |
| SW-A-DEIE | 10.99.99.21/24 | SVI VLAN 99 |
| SW-A-DCEE | 10.99.99.22/24 | SVI VLAN 99 |
| SW-A-DMME | 10.99.99.23/24 | SVI VLAN 99 |
| SW-A-DIS | 10.99.99.24/24 | SVI VLAN 99 |
| R-CORE | 10.99.0.1/32 | Loopback0 |
| R-EDGE | 10.99.0.2/32 | Loopback0 |

All distribution and access switches use `10.99.99.1`, the VLAN 99 HSRP virtual
address, as their default gateway. Management reachability therefore survives the
loss of either core switch.

## 5. Server and host addressing

| Host | VLAN | IP | Role |
|------|------|----|------|
| VM-AUTO | 99 | 10.99.99.100/24 | Netmiko + Ansible automation host |
| VM-ZABBIX | 40 | 10.10.40.20/24 | Zabbix 6.x server, SNMP poller |
| VM-DHCP/WEB | 40 | 10.10.40.10/24 | DHCP/DNS and web server for reachability tests |
| PC-DEIE-1 | 10 | 10.10.10.101/24 | Test host |
| PC-DEIE-2 | 10 | 10.10.10.102/24 | Test host |
| PC-DCEE-1 | 20 | 10.10.20.101/24 | Test host |
| PC-DCEE-2 | 20 | 10.10.20.102/24 | Test host |
| PC-DMME-1 | 30 | 10.10.30.101/24 | Test host |
| PC-DMME-2 | 30 | 10.10.30.102/24 | Test host |
| PC-DIS-1 | 40 | 10.10.40.101/24 | Test host |
| PC-DIS-2 | 40 | 10.10.40.102/24 | Test host |

DHCP pools (served by VM-DHCP) allocate `.150`–`.200` in each department VLAN.
Test hosts use static addresses so that ACL test results are reproducible.

## 6. Routing

- **OSPF process 1, area 0** on R-EDGE, R-CORE and SW-CORE. All department
  subnets, the management VLAN, the point-to-point links and both router
  loopbacks are advertised into area 0.
- **Static default route** on R-EDGE toward the simulated internet:
  `ip route 0.0.0.0 0.0.0.0 192.168.25.2`, advertised into OSPF with
  `default-information originate` so the interior devices learn it.

  The outside address was originally planned as `203.0.113.2/24`, a documentation
  range. The GNS3 NAT node actually serves `192.168.25.0/24` with the gateway at
  `.2`, so the plan was corrected to match the simulator. `192.168.25.10` is used
  statically because it sits below the DHCP pool, which keeps the address stable
  across restarts and makes NAT translations reproducible for testing.
- **NAT overload (PAT)** on R-EDGE, outside interface Gi0/0. Only VLAN_DEIE
  (10.10.10.0/24) and VLAN_DCEE (10.10.20.0/24) are matched by the NAT ACL, so
  only those two departments obtain internet egress. VLAN_DMME, VLAN_DIS and
  the management VLAN have no translation entry and therefore no internet access.

## 7. Design decisions

### 7.1 Centralised inter-VLAN routing on a redundant core pair

All department SVIs are configured on the SW-CORE pair rather than distributed
across the SW-D-* distribution switches. Distribution and access switches operate
at Layer 2 and carry VLANs over 802.1Q trunks.

Rationale: with only four user VLANs and a single site, centralising the SVIs
gives one enforcement point for the inter-department ACL policy. Every packet
crossing a VLAN boundary must transit the core, so applying the policy inbound on
the SVIs guarantees it cannot be bypassed. Distributing the SVIs would require
the same ACL to be replicated on three distribution switches, multiplying the
opportunity for inconsistency, which is the most common cause of policy failure
in production networks.

### 7.2 Core redundancy with HSRP

A single core switch would be both a single point of failure and a traffic
concentration point: its loss would sever every inter-VLAN path in the campus and
isolate all four departments from each other and from the internet. The core is
therefore deployed as a pair, SW-CORE-1 and SW-CORE-2, running HSRP on every SVI.

Load distribution is achieved by alternating the active role per VLAN rather than
leaving one switch idle as a cold standby. VLANs 10, 20 and 99 are active on
SW-CORE-1 and VLANs 30 and 40 on SW-CORE-2, with STP root priorities aligned to
match so that the Layer 2 forwarding path follows the Layer 3 gateway. Without
that alignment, traffic would traverse the peer link on every hop for the VLANs
whose STP root and HSRP active switch disagree.

R-CORE is dual-homed to both cores, so no single link or chassis failure isolates
the campus from the edge router.

Trade-off, and the principal cost of this decision: the inter-department ACLs must
now exist identically on two devices. Configuration drift between the pair would
produce policy that succeeds or fails depending on which core happens to be
forwarding, which is difficult to diagnose. This risk is the direct justification
for managing switch configuration with Ansible rather than by hand: an idempotent
playbook applied to both cores from a single source of truth makes divergence
structurally impossible, and `ansible-playbook --check` provides continuous
verification that the two remain in step.

### 7.3 Separate management plane on VLAN 99



Management traffic is isolated in VLAN 99 with no user hosts. SSH is permitted
only from this VLAN, and VM-AUTO is the only host in it. This means an ACL
misconfiguration in a department VLAN cannot lock the team out of the devices,
which is the highest-likelihood risk in the MOP risk register.

Routers are managed on loopback addresses rather than a physical interface so
that management reachability survives the failure of any single link, provided
OSPF still has a path.

## 8. Open items

- Confirm the GNS3 interface numbering once devices are placed; the Gi0/x
  assignments above may shift depending on IOSv adapter configuration.
- Confirm DHCP scope options with the VM-DHCP build.
