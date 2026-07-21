# EE8203 — Department-Level Campus Network Design & Management

Group project for EE8203 (Design and Management of Data Networks), Department of
Electrical and Information Engineering, Faculty of Engineering, University of Ruhuna.

Design, implementation, automation and monitoring of a campus data network
interconnecting four departments: DEIE, DCEE, DMME and DIS.

## Environment

- Simulation: GNS3 2.2.x with the GNS3 VM
- Network devices: Cisco IOSv (routers) and IOSvL2 (switches)
- Automation host: Ubuntu 22.04 (Python 3 + Netmiko, Ansible)
- Monitoring: Zabbix 6.x LTS with SNMPv2c

## Repository layout

| Path | Contents |
|------|----------|
| `docs/` | Design document, IP/VLAN plan, MOP, final report |
| `docs/diagrams/` | Topology diagrams |
| `docs/evidence/` | Test screenshots, reachability matrix evidence |
| `configs/baseline/` | Manual baseline device configurations |
| `netmiko/` | Python automation scripts for routers and SNMP |
| `netmiko/inventory/` | Device inventory (JSON/YAML) — no hardcoded parameters |
| `netmiko/logs/` | Timestamped script execution logs |
| `ansible/` | Ansible project for switch automation |
| `ansible/roles/` | Roles: vlans, trunking, access ports, STP |
| `ansible/playbooks/rollback/` | Rollback playbook |
| `zabbix/` | Dashboard JSON export, template notes |

## Status

Work in progress. See `docs/` for the current design document and MOP.
