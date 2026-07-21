# Design Document 2 — Topology and Port Map

EE8203 Campus Network — Faculty of Engineering, University of Ruhuna
Version 0.1

## 1. Device inventory

| Hostname | GNS3 template | RAM | Role |
|----------|---------------|-----|------|
| R-EDGE | Cisco IOSv 15.9(3)M6 | 512 MB | Edge/WAN router, default route, NAT overload |
| R-CORE | Cisco IOSv 15.9(3)M6 | 512 MB | Core router, OSPF area 0, dual-homed to core pair |
| SW-CORE-1 | Cisco IOSvL2 15.2 | 768 MB | Core L3 switch, SVIs, HSRP active for VLAN 10/20/99 |
| SW-CORE-2 | Cisco IOSvL2 15.2 | 768 MB | Core L3 switch, SVIs, HSRP active for VLAN 30/40 |
| SW-D-DEIE | Cisco IOSvL2 15.2 | 768 MB | Distribution switch, DEIE |
| SW-D-DCEE | Cisco IOSvL2 15.2 | 768 MB | Distribution switch, DCEE |
| SW-D-DMME | Cisco IOSvL2 15.2 | 768 MB | Distribution switch, DMME |
| SW-A-DEIE | Cisco IOSvL2 15.2 | 768 MB | Access switch, DEIE |
| SW-A-DCEE | Cisco IOSvL2 15.2 | 768 MB | Access switch, DCEE |
| SW-A-DMME | Cisco IOSvL2 15.2 | 768 MB | Access switch, DMME |
| SW-A-DIS | Cisco IOSvL2 15.2 | 768 MB | Access switch, DIS server farm |
| VM-AUTO | Ubuntu 22.04 | 2 GB | Netmiko + Ansible automation host |
| VM-ZABBIX | Ubuntu 22.04 | 2.5 GB | Zabbix 6.x LTS server |
| VM-DHCP | Ubuntu 22.04 / lightweight | 512 MB | DHCP, DNS and web server |
| PC-* ×8 | GNS3 VPCS | negligible | Test hosts, two per department |
| Internet | NAT cloud | — | Simulated internet, 203.0.113.1 |

Total: 11 network devices, 3 servers, 8 test hosts.

## 2. Physical link map

### 2.1 Edge and core routing

| From | Port | To | Port | Type |
|------|------|----|----- |------|
| Internet (NAT) | — | R-EDGE | Gi0/0 | Routed, 203.0.113.0/24 |
| R-EDGE | Gi0/1 | R-CORE | Gi0/1 | Routed /30 |
| R-CORE | Gi0/2 | SW-CORE-1 | Gi0/0 | Routed /30 |
| R-CORE | Gi0/3 | SW-CORE-2 | Gi0/0 | Routed /30 |

### 2.2 Core peer link (EtherChannel Po1)

| From | Port | To | Port | Type |
|------|------|----|----- |------|
| SW-CORE-1 | Gi0/1 | SW-CORE-2 | Gi0/1 | Po1 member, 802.1Q trunk |
| SW-CORE-1 | Gi0/2 | SW-CORE-2 | Gi0/2 | Po1 member, 802.1Q trunk |

Two physical links bundled with LACP into Port-channel 1. A redundant core pair
joined by a single peer link would leave that link as an unprotected single point
of failure carrying all HSRP hellos and all inter-core VLAN traffic; bundling two
links removes it and doubles the available peer bandwidth.

### 2.3 Distribution and DIS access uplinks (dual-homed)

Every distribution switch, and the DIS access switch, connects to both cores.

| From | Port | To | Port | Type |
|------|------|----|----- |------|
| SW-D-DEIE | Gi0/0 | SW-CORE-1 | Gi0/3 | 802.1Q trunk |
| SW-D-DEIE | Gi0/1 | SW-CORE-2 | Gi0/3 | 802.1Q trunk |
| SW-D-DCEE | Gi0/0 | SW-CORE-1 | Gi1/0 | 802.1Q trunk |
| SW-D-DCEE | Gi0/1 | SW-CORE-2 | Gi1/0 | 802.1Q trunk |
| SW-D-DMME | Gi0/0 | SW-CORE-1 | Gi1/1 | 802.1Q trunk |
| SW-D-DMME | Gi0/1 | SW-CORE-2 | Gi1/1 | 802.1Q trunk |
| SW-A-DIS | Gi0/0 | SW-CORE-1 | Gi1/2 | 802.1Q trunk |
| SW-A-DIS | Gi0/1 | SW-CORE-2 | Gi1/2 | 802.1Q trunk |

SW-A-DIS attaches directly to the core rather than through a distribution switch
because the DIS server farm has no separate distribution tier in this design.

Dual-homing deliberately creates a Layer 2 loop at each site. This is expected:
spanning tree blocks the redundant path and unblocks it automatically if the
primary uplink fails. STP root placement is aligned with the HSRP active role so
that the unblocked path leads to the active gateway.

### 2.4 Access layer uplinks

| From | Port | To | Port | Type |
|------|------|----|----- |------|
| SW-A-DEIE | Gi0/0 | SW-D-DEIE | Gi0/2 | 802.1Q trunk |
| SW-A-DCEE | Gi0/0 | SW-D-DCEE | Gi0/2 | 802.1Q trunk |
| SW-A-DMME | Gi0/0 | SW-D-DMME | Gi0/2 | 802.1Q trunk |

Access switches are single-homed to their own department distribution switch.
The failure domain of that link is one department's user population, which is
acceptable; the redundancy budget is spent at the core, where a failure would
affect the whole campus.

### 2.5 End hosts and servers

| Host | Port on switch | Switch | Access VLAN |
|------|----------------|--------|-------------|
| PC-DEIE-1 | Gi1/0 | SW-A-DEIE | 10 |
| PC-DEIE-2 | Gi1/1 | SW-A-DEIE | 10 |
| PC-DCEE-1 | Gi1/0 | SW-A-DCEE | 20 |
| PC-DCEE-2 | Gi1/1 | SW-A-DCEE | 20 |
| PC-DMME-1 | Gi1/0 | SW-A-DMME | 30 |
| PC-DMME-2 | Gi1/1 | SW-A-DMME | 30 |
| PC-DIS-1 | Gi1/0 | SW-A-DIS | 40 |
| PC-DIS-2 | Gi1/1 | SW-A-DIS | 40 |
| VM-DHCP | Gi1/3 | SW-A-DIS | 40 |
| VM-ZABBIX | Gi2/0 | SW-A-DIS | 40 |
| VM-AUTO | Gi2/1 | SW-A-DIS | 99 |

VM-AUTO sits in the management VLAN on the DIS access switch. DIS is the faculty
IT hub, so hosting the automation platform there is consistent with the scenario,
and SW-A-DIS is dual-homed to both cores, so automation reachability survives the
loss of either core switch.

## 3. Memory budget and staged startup

The full topology exceeds the 16 GB available on the build host:

| Group | Devices | RAM |
|-------|---------|-----|
| Core and routing | R-EDGE, R-CORE, SW-CORE-1, SW-CORE-2 | 2.6 GB |
| Distribution | SW-D-DEIE, SW-D-DCEE, SW-D-DMME | 2.3 GB |
| Access | SW-A-DEIE, SW-A-DCEE, SW-A-DMME, SW-A-DIS | 3.1 GB |
| Servers | VM-AUTO, VM-ZABBIX, VM-DHCP | 5.0 GB |
| GNS3 VM overhead | — | ~1.5 GB |
| Host operating system | — | ~4.0 GB |
| **Total if all running** | | **~18.5 GB** |

The topology is therefore never run in full. Devices are started in phases
according to the task in hand:

| Phase | Devices started | Approx. RAM |
|-------|-----------------|-------------|
| Baseline routing and trunking | Core group + distribution | 9.4 GB |
| VLAN and host connectivity | Core + distribution + access + VPCS | 12.5 GB |
| ACL policy testing | All network devices + VPCS, no servers | 12.5 GB |
| Netmiko and Ansible automation | All network devices + VM-AUTO | 14.5 GB |
| Zabbix monitoring | Core + distribution + SW-A-DIS + VM-ZABBIX | 11.0 GB |

VM-ZABBIX and VM-AUTO are not run at the same time except during the final
end-to-end demonstration, when VM-DHCP and unused VPCS nodes are stopped to make
room.
