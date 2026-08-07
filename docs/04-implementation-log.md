# Implementation Log

EE8203 Campus Network — record of deviations, faults and operating constraints
encountered during the build.

This document exists to support the Method of Procedure, particularly Section 4
(risk assessment) and Section 8 (post-implementation review), and the final
report's "Challenges and Lessons Learned" chapter. Everything here was
encountered during the actual build rather than anticipated in advance.

## 1. Deviations from the design

| Planned | Actual | Reason |
|---------|--------|--------|
| Outside subnet `203.0.113.0/24` | `192.168.25.0/24`, gateway `.2` | `203.0.113.0/24` is a documentation range with no existence in the simulator. The GNS3 NAT node serves `192.168.25.0/24`. R-EDGE uses `.10` statically, chosen below the DHCP pool so the address survives restarts and NAT translations stay reproducible. |
| Distribution switches as Layer 3 | Layer 2 only | All SVIs are centralised on the core pair so the inter-department policy has a single enforcement point. Distribution and access switches carry VLANs over 802.1Q trunks and are managed via `ip default-gateway`. |
| Single SW-CORE | Redundant pair with HSRP | A single core would be a single point of failure for all inter-VLAN routing. The pair alternates the active role per VLAN so both carry traffic. |
| Trunks carrying all VLANs | Pruned per department | Each downlink carries only its own department VLAN plus management, confining broadcast domains and giving the Ansible project a genuine use for `host_vars`. |
| VM-AUTO with a NAT adapter for internet | Single adapter in VLAN 99 | GNS3 repeatedly reassigned the second adapter. A single adapter removes the conflict; internet is obtained through a temporary NAT exception when required. |

## 2. Faults encountered and their resolution

### 2.1 GNS3 node settings are copied from the template at creation

Changing a template in Preferences does not affect nodes already on the canvas.
VM-AUTO kept recreating a second network adapter because the node still declared
two, even after the template was set to one. The fix is to edit the node itself
rather than the template.

The same applies to the server a node runs on. This cost several hours and is
worth checking first whenever a GNS3 node ignores a preference change.

### 2.2 Frames silently discarded on cross-server links

VPCS nodes created on the local server, linked to switches running inside the
GNS3 VM, produced links that reported connected while passing no traffic. The
switch port showed `connected`, the host's MAC never appeared in the MAC address
table, and no error was raised.

The cause is `ubridge` on Windows bridging a VMnet interface into a UDP tunnel;
stale bridges from deleted nodes persist in the running server process and are
not cleared by deleting the node. Moving all VPCS nodes onto the GNS3 VM removed
the cross-server path entirely and reduced host-to-host latency from 100–460 ms
to 5–12 ms.

### 2.3 Omitting a command does not remove it

The SW-CORE-2 configuration block was applied to SW-CORE-1 in error. Re-applying
the correct block did not fix it, because that block simply omits the commands
that were wrongly set. HSRP priorities accumulated and both switches ended up
with priority 110 on every group.

Correcting it required explicitly setting the intended values. This is the
clearest practical argument for declarative configuration management: "apply the
intended configuration" and "re-run the configuration file" are different
operations, and only the first converges.

### 2.4 A FULL OSPF adjacency does not mean routing works

After R-CORE was wiped for the reset-and-replay test, its interface reverted to
the default broadcast network type while SW-CORE-1 retained point-to-point. The
adjacency reached FULL and `show ip ospf neighbor` appeared healthy, but each
side described the link differently in its router LSA and the loopback route was
never installed.

Network type mismatches are not rejected by OSPF. The symptom is a neighbour
that looks correct while the device remains unreachable.

### 2.5 An unreadable section is not an absent one

The router script initially reported correctly configured interfaces as missing
because the device was too loaded to answer and the read returned nothing. In a
live run this would have re-pushed existing configuration, defeating the
idempotency the design depends on.

The check now retries an empty read before concluding a section is absent. The
underlying principle is that an idempotency check compares intent with observed
state, so a failure to observe must never be reported as a difference.

### 2.6 A configuration can be correct and the network still broken

After the rollback and rebuild of SW-A-DEIE, `ansible-playbook --check` reported
zero changes, every interface showed `connected` in the right VLAN, and the
running configuration of each port was exactly as intended. Hosts could not
reach their gateway.

`show vlan brief` reported VLAN 10 as `act/lshut`: the VLAN existed, held the
right name and the right ports, and was locally shut down. A shut VLAN forwards
nothing and has no spanning tree instance, which is why `show spanning-tree
vlan 10` reported that the instance did not exist and the MAC address table was
empty.

The rollback left the VLAN in that state and the rebuild recreated it without
clearing the shutdown, because the role did not manage that attribute at all.
Ansible was reporting truthfully: every line it managed was correct. The set of
lines it managed was incomplete.

No amount of `--check` would have revealed this, because `--check` compares
intent against reality and the intent itself was silent on the point. Only
traffic exposed it. The lesson is recorded in the MOP test plan: a rollback is
verified by a host reaching its gateway, not by a playbook exiting cleanly.

### 2.7 Netmiko defaults assume physical hardware

The first full run failed on every device with pattern and read timeouts rather
than authentication errors. Two separate causes:

- Timeouts written for hardware that answers in milliseconds. Raised connection,
  authentication and read timeouts, disabled `fast_cli`, added connection
  retries.
- `send_command` waits for the command to be echoed back and the prompt to
  reappear in an expected form. A loaded emulated device returns output in
  fragments and the match fails regardless of timeout. Replaced with
  `send_command_timing`, which reads until the device falls silent.

Netmiko's own `exit_config_mode()` and `save_config()` do not accept the read
timeout passed to `send_config_set`, so those steps are issued as plain commands
instead.

### 2.8 Legacy device crypto against modern clients

IOS 15.x offers only SHA-1 key exchange and RSA host keys, both disabled by
default in OpenSSH 8.8 and later. Direct `ssh` from Ubuntu 22.04 fails with "no
matching key exchange method found".

Resolved with a client configuration scoped to `10.99.*` only, so the exception
applies to the legacy estate and not to every connection the host makes.
Netmiko was unaffected because Paramiko still permits those algorithms.

### 2.9 Emulated data planes are not suitable for bulk transfer

Installing packages on VM-AUTO through the campus network took over thirty
minutes for `apt update` alone, because every packet crosses five
software-forwarding devices. The same install completed in minutes over the
host's NAT interface.

This does not affect the assessed work: Netmiko and Ansible transfer
configuration text measured in kilobytes, and SNMP polling is smaller still.
Separating bulk provisioning from in-band management is normal operational
practice rather than a workaround.

## 3. Operating constraints

Measured on the build host (16 GB RAM, i7-11800H, GNS3 VM at 6–8 vCPU / 10 GB).

| Devices running | Control plane latency | Packet loss | Automation |
|-----------------|----------------------|-------------|------------|
| 11 (full topology) | 300–2300 ms | 30–80% | Fails with timeouts |
| 4–5 | 11–20 ms | 0% | Works reliably |

Performance also degrades with GNS3 VM uptime at a constant device count; a
restart restores it but takes around thirty minutes, so stopping individual
nodes is the cheaper remedy.

IOS-reported CPU is misleading under this contention. A switch reporting 42%
was in fact severely starved, because IOS measures busy time as a fraction of
the time it is scheduled rather than wall clock time.

**Operational rule:** before any automation run, confirm `ping` to the target is
under about 50 ms with no loss. Poor results call for stopping devices, not for
raising timeouts. Schedule the recorded demonstration shortly after a restart.

## 4. Open items

| Item | Status | Action required |
|------|--------|-----------------|
| NAT exception for `10.99.99.0/24` on R-EDGE | **Still applied** | Must be removed before any assessed demonstration. It contradicts the documented policy that only VLAN_DEIE and VLAN_DCEE obtain internet egress. Verify with `show ip access-lists NAT_PERMITTED`. |
| Device credentials in `configs/baseline/*.cfg` | Committed in plaintext | The repository is public. Replace with placeholders before submission, or accept and note as a lab-only credential. |
| DCEE to DIS web access | Deny half tested only | The permitted half (HTTP/HTTPS) requires a web server at `10.10.40.10`. Test once VM-DHCP/WEB is deployed; it is the clearest demonstration that the policy filters by protocol and not only by subnet. |
| VM-ZABBIX, VM-DHCP | Not deployed | Install packages over the host NAT interface before attaching to the topology, and set `Adapters = 1` on each node after creating it. |

## 5. Material for the MOP risk register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| ACL blocks management access | Medium | High | SSH is restricted by `access-class` on the VTY lines rather than by data plane ACLs, so a fault in a department list cannot remove management access. |
| Configuration drift between the core pair | Medium | High | Both cores must hold identical ACLs and VLAN configuration. Managed by Ansible from a single source of truth; verified with `ansible-playbook --check`. |
| Automation applies configuration it cannot verify | Low | High | Section reads are retried before a section is treated as absent, so an unreadable device is reported as failed rather than reconfigured. |
| Core switch reboot interrupts automation | Medium | Medium | VLAN 99 is a flat segment reaching the automation host through SW-CORE-1. Any change restarting that switch will interrupt a run in progress. |
| Wiped device unreachable by automation | High | Medium | A console bootstrap providing address, credentials, SSH and a matching OSPF network type is required before the scripts can run. Documented in `configs/bootstrap/`. |
| Simulator performance collapse during demonstration | Medium | High | Run only the devices required for the task; restart GNS3 before recording. |
