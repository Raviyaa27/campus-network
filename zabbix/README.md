# Zabbix monitoring

Zabbix 6.0 LTS on VM-ZABBIX (`10.10.40.20`), polling all eleven network devices
over SNMPv2c.

## Monitored hosts

All eleven devices, in host group `Campus Network`, each linked to the template
`Cisco IOS by SNMP`.

| Host | Address |
|------|---------|
| R-CORE | 10.99.0.1 |
| R-EDGE | 10.99.0.2 |
| SW-CORE-1 | 10.99.99.2 |
| SW-CORE-2 | 10.99.99.3 |
| SW-D-DEIE | 10.99.99.11 |
| SW-D-DCEE | 10.99.99.12 |
| SW-D-DMME | 10.99.99.13 |
| SW-A-DEIE | 10.99.99.21 |
| SW-A-DCEE | 10.99.99.22 |
| SW-A-DMME | 10.99.99.23 |
| SW-A-DIS | 10.99.99.24 |

The brief names the template `Template Net Cisco IOS SNMPv2`, which was its
title in Zabbix 5.0. Zabbix 6.0 renamed it to `Cisco IOS by SNMP`; it is the
same template.

The community string is held once as the global macro `{$SNMP_COMMUNITY}` and
inherited by every host, rather than being entered eleven times. It was applied
to the devices themselves by `netmiko/deploy_snmp.py`, so the value exists in
exactly two places: the inventory the script reads, and this macro.

## Triggers

| Requirement | Trigger | Source |
|-------------|---------|--------|
| Device unreachable, more than three consecutive polls | Unavailable by ICMP ping, `max(/host/icmpping,#3)=0` | Template |
| Interface down | Interface *: Link down, created per discovered interface | Template |
| CPU above 80% for more than 60 seconds | `min(/host/system.cpu.util,1m)>80` | Defined for this project |
| Student defined | Device restarted, `last(/host/system.hw.uptime[hrSystemUptime.0])<10m` | Defined for this project |

### Why the CPU trigger is only on the routers

IOSvL2 does not implement `CISCO-PROCESS-MIB`, so the CPU item returns no data
on the switches. The trigger is defined on R-CORE and R-EDGE, which run IOSv and
report the OID normally. On physical hardware the same template would collect it
from every device.

### Why the restart trigger was chosen

The campus has a redundant core pair running HSRP, so a single switch or router
restarting may cause no visible outage: traffic fails over, no interface stays
down for long, and no other trigger fires. Users notice nothing.

An unplanned restart nonetheless means something happened - power loss, a crash,
or an unsaved configuration that has now reverted - and the network is running
without redundancy until the device returns. It is a fault this particular
design would otherwise conceal, which is why it is worth alerting on.

The trigger uses `hrSystemUptime` rather than `sysUpTime`. The latter measures
how long the SNMP agent has been running and resets when SNMP is reconfigured,
which the automation does routinely; using it would raise a false alarm on every
`deploy_snmp.py` run.

## Dashboard

`EE8203_FoE-UoR-Network_dashboard.json` is the export of the dashboard named
**FoE-UoR Network**, containing five widgets:

| Widget | Purpose |
|--------|---------|
| Map | Host availability across the campus topology |
| Problems by severity | Open trigger count by severity |
| Graph | Interface traffic for the core switches, both directions |
| Problems | Live problem list |
| Host availability | SNMP availability summary |

### How it was exported

Zabbix 6.0 has no user interface export for global dashboards; the operation is
only available through the API. The file is the response to a `dashboard.get`
call:

```
TOKEN=$(curl -s -X POST -H 'Content-Type: application/json-rpc' \
  -d '{"jsonrpc":"2.0","method":"user.login","params":{"username":"Admin","password":"<password>"},"id":1}' \
  http://localhost/zabbix/api_jsonrpc.php | python3 -c 'import sys,json;print(json.load(sys.stdin)["result"])')

curl -s -X POST -H 'Content-Type: application/json-rpc' \
  -d "{\"jsonrpc\":\"2.0\",\"method\":\"dashboard.get\",\"params\":{\"output\":\"extend\",\"selectPages\":\"extend\",\"filter\":{\"name\":\"FoE-UoR Network\"}},\"auth\":\"$TOKEN\",\"id\":2}" \
  http://localhost/zabbix/api_jsonrpc.php | python3 -m json.tool > EE8203_FoE-UoR-Network_dashboard.json
```

The file retains the full API response, including the `jsonrpc` and `id`
envelope, rather than only the dashboard object. That is deliberate: it records
how the export was obtained and can be verified against the API by anyone
repeating the call.

## Monitoring path

VM-ZABBIX sits in VLAN 40 and polls management addresses in VLAN 99 and on the
router loopbacks, so every query crosses a VLAN boundary and is evaluated by the
inter-department access policy. `ACL_DIS_IN` on the core pair permits UDP 161 and
ICMP from `10.10.40.20` to `10.99.99.0/24` and `10.99.0.0/24`, and nothing else
from the server farm reaches the management plane.

Those four entries were written when the access control policy was designed,
before this host existed.
