# Design Document 3 — Inter-Department Access Control Policy

EE8203 Campus Network — Faculty of Engineering, University of Ruhuna
Version 1.0

## 1. Policy statement

The assignment brief specifies five inter-department policies. It also requires
that the default position be an explicit deny. The brief does not state a position
for every pair of departments, so the unstated pairs have been resolved as **deny**,
consistent with the stated default-deny requirement and with the restrictive
character of the policies that are specified.

The complete policy is therefore:

| Source | Destination | Action | Origin |
|--------|-------------|--------|--------|
| VLAN_DEIE | VLAN_DIS | Permit all | Specified in brief |
| VLAN_DCEE | VLAN_DIS | Permit HTTP/HTTPS only | Specified in brief |
| VLAN_DMME | VLAN_DIS | Deny all | Specified in brief |
| VLAN_DCEE | VLAN_DEIE | Deny all | Specified in brief |
| VLAN_DMME | VLAN_DCEE | Deny all | Specified in brief |
| VLAN_DEIE | VLAN_DCEE | Deny all | Default deny |
| VLAN_DEIE | VLAN_DMME | Deny all | Default deny |
| VLAN_DCEE | VLAN_DMME | Deny all | Default deny |
| VLAN_DMME | VLAN_DEIE | Deny all | Default deny |
| VLAN_DIS | VLAN_DEIE | Permit all | Return path for permitted session |
| VLAN_DIS | VLAN_DCEE | Permit HTTP/HTTPS replies only | Return path for permitted session |
| VLAN_DIS | VLAN_DMME | Deny all | Default deny |
| VM-ZABBIX | All managed devices | Permit SNMP and ICMP | Specified in brief |
| MGMT VLAN | All devices | Permit SSH | Specified in brief |
| Any | Any | Deny | Implicit deny at end of every list |

### 1.1 Why the VLAN_DIS rows exist

Access control lists on IOS are stateless. They evaluate each packet in isolation
and hold no record of a session having been established. When a DEIE host sends a
request to a server in DIS, the reply is a separate packet that enters the core
through the VLAN 40 SVI and is evaluated against that interface's inbound list.

Without an explicit permit for the return direction, replies are discarded and the
permitted DEIE to DIS policy appears not to work, even though the forward rule is
correct. The VLAN_DIS rows are therefore not additional policy; they are the return
half of policy already stated.

## 2. Placement

All lists are applied **inbound on the department SVI** on **both core switches**.

Inbound at the source is the standard placement for this kind of policy. The packet
is discarded at the first Layer 3 hop, before it consumes bandwidth across the core
or reaches the destination segment. Applying the equivalent list outbound at the
destination would permit denied traffic to traverse the entire campus before being
dropped.

| Access list | Interface | Direction | Applied on |
|-------------|-----------|-----------|------------|
| ACL_DEIE_IN | Vlan10 | in | SW-CORE-1 and SW-CORE-2 |
| ACL_DCEE_IN | Vlan20 | in | SW-CORE-1 and SW-CORE-2 |
| ACL_DMME_IN | Vlan30 | in | SW-CORE-1 and SW-CORE-2 |
| ACL_DIS_IN | Vlan40 | in | SW-CORE-1 and SW-CORE-2 |
| MGMT_SSH | line vty 0 15 | in (access-class) | All devices |

Because the SVIs exist on both members of the redundant core pair, every list must
exist identically on both. A difference between the two would produce policy that
succeeds or fails depending on which core happened to be the active gateway at the
time, which is difficult to diagnose. This requirement is the direct justification
for managing switch configuration with Ansible rather than by hand.

### 2.1 SSH restriction on the control plane

The requirement that SSH be reachable only from VLAN 99 is enforced with an
`access-class` on the VTY lines rather than with data plane entries on each SVI.

Filtering management traffic on every interface would require a correct entry on
every SVI of every device, and any interface added later without that entry would
silently open a path. Applying the restriction where the session actually
terminates means it holds regardless of the route the packet took to arrive.

## 3. Access list definitions

Each list ends with `permit ip <subnet> any`. This is deliberate and is required
for correct operation beyond user traffic: HSRP hello packets from the peer core
arrive inbound on each SVI and are sourced from the local subnet. A narrower final
entry would discard them, and both cores would then declare themselves active for
every group.

### ACL_DEIE_IN — applied to Vlan10 inbound

```
permit ip 10.10.10.0 0.0.0.255 10.10.40.0 0.0.0.255
deny   ip 10.10.10.0 0.0.0.255 10.10.20.0 0.0.0.255
deny   ip 10.10.10.0 0.0.0.255 10.10.30.0 0.0.0.255
deny   ip 10.10.10.0 0.0.0.255 10.99.99.0 0.0.0.255
deny   ip 10.10.10.0 0.0.0.255 10.99.0.0 0.0.0.255
permit ip 10.10.10.0 0.0.0.255 any
```

### ACL_DCEE_IN — applied to Vlan20 inbound

```
permit tcp 10.10.20.0 0.0.0.255 10.10.40.0 0.0.0.255 eq 80
permit tcp 10.10.20.0 0.0.0.255 10.10.40.0 0.0.0.255 eq 443
deny   ip  10.10.20.0 0.0.0.255 10.10.40.0 0.0.0.255
deny   ip  10.10.20.0 0.0.0.255 10.10.10.0 0.0.0.255
deny   ip  10.10.20.0 0.0.0.255 10.10.30.0 0.0.0.255
deny   ip  10.10.20.0 0.0.0.255 10.99.99.0 0.0.0.255
deny   ip  10.10.20.0 0.0.0.255 10.99.0.0 0.0.0.255
permit ip  10.10.20.0 0.0.0.255 any
```

The two permit entries precede the deny to the same subnet. Order is significant:
access lists are evaluated top to bottom and the first match wins, so reversing
these would deny web traffic before the permit was ever reached.

### ACL_DMME_IN — applied to Vlan30 inbound

```
deny   ip 10.10.30.0 0.0.0.255 10.10.40.0 0.0.0.255
deny   ip 10.10.30.0 0.0.0.255 10.10.10.0 0.0.0.255
deny   ip 10.10.30.0 0.0.0.255 10.10.20.0 0.0.0.255
deny   ip 10.10.30.0 0.0.0.255 10.99.99.0 0.0.0.255
deny   ip 10.10.30.0 0.0.0.255 10.99.0.0 0.0.0.255
permit ip 10.10.30.0 0.0.0.255 any
```

### ACL_DIS_IN — applied to Vlan40 inbound

```
permit udp  host 10.10.40.20 10.99.99.0 0.0.0.255 eq 161
permit udp  host 10.10.40.20 10.99.0.0 0.0.0.255 eq 161
permit icmp host 10.10.40.20 10.99.99.0 0.0.0.255
permit icmp host 10.10.40.20 10.99.0.0 0.0.0.255
permit ip   10.10.40.0 0.0.0.255 10.10.10.0 0.0.0.255
permit tcp  10.10.40.0 0.0.0.255 eq 80  10.10.20.0 0.0.0.255
permit tcp  10.10.40.0 0.0.0.255 eq 443 10.10.20.0 0.0.0.255
deny   ip   10.10.40.0 0.0.0.255 10.10.20.0 0.0.0.255
deny   ip   10.10.40.0 0.0.0.255 10.10.30.0 0.0.0.255
deny   ip   10.10.40.0 0.0.0.255 10.99.99.0 0.0.0.255
deny   ip   10.10.40.0 0.0.0.255 10.99.0.0 0.0.0.255
permit ip   10.10.40.0 0.0.0.255 any
```

The four monitoring entries are placed above the entries denying access to the
management plane. Placed below them, the general deny would match first and the
monitoring server would be unable to poll any device.

### MGMT_SSH — applied as access-class on the VTY lines

```
permit 10.99.99.0 0.0.0.255
```

## 4. Internet access policy

Internet egress is not enforced by these lists. It is enforced by the NAT
configuration on R-EDGE, where only the DEIE and DCEE subnets appear in the
`NAT_PERMITTED` list. Packets from VLAN_DMME, VLAN_DIS and the management VLAN
reach R-EDGE but have no translation entry and are discarded there.

Enforcing the two policies at different layers is intentional. Department to
department policy belongs at the first Layer 3 hop; internet policy belongs at the
boundary where translation occurs. Neither can be bypassed by circumventing the
other.

## 5. Test results

Tested from one representative host per department, five ICMP echo requests and one
traceroute per cell. Evidence is in `Screenshots/`, with `acl-` prefixed files
recording the post-implementation state and the unprefixed files recording the
baseline before any list was applied.

| From ↓ / To → | DEIE | DCEE | DMME | DIS |
|---------------|------|------|------|-----|
| **DEIE** | Permit | Deny | Deny | Permit |
| **DCEE** | Deny | Permit | Deny | Deny (ICMP) |
| **DMME** | Deny | Deny | Permit | Deny |
| **DIS** | Permit | Deny | Deny | Permit |

Every cell matches the policy in section 1.

Denied traffic is rejected with ICMP type 3 code 13, communication administratively
prohibited, returned by the SVI that enforced the policy. The rejection is explicit
rather than a silent discard, so the test output identifies both that the traffic
was denied and which device denied it.

The DCEE to DIS cell records the denial of ICMP. The permitted half of that policy,
HTTP and HTTPS, requires a web server in the server farm and is tested separately
once VM-DHCP/WEB is deployed.

### 5.1 Access list counters as corroborating evidence

Match counters were cleared before the test run and captured afterwards from both
core switches. The counts divide cleanly between the two:

| Access list | Denies matched on SW-CORE-1 | Denies matched on SW-CORE-2 |
|-------------|------------------------------|------------------------------|
| ACL_DEIE_IN | 8, 8 | none |
| ACL_DCEE_IN | 8, 8, 8 | none |
| ACL_DMME_IN | none | 8, 8, 8 |
| ACL_DIS_IN | none | 8, 8 |

SW-CORE-1 is the HSRP active gateway for VLANs 10 and 20 and enforces those
policies. SW-CORE-2 is active for VLANs 30 and 40 and enforces those. Neither
switch sees the other's traffic in normal operation.

This confirms the load distribution designed in the addressing plan through a
mechanism independent of the HSRP state output, and demonstrates that both cores
carry production traffic rather than one sitting idle as a standby. Each count of
eight is five ICMP echo requests plus three traceroute probes.

## 6. Rollback

To remove the policy from an interface without deleting the list:

```
interface Vlan10
 no ip access-group ACL_DEIE_IN in
```

If an access list denies management access, connect to the affected switch by
console and remove the group from the affected interface. Because SSH is restricted
by `access-class` on the VTY lines rather than by these lists, a fault in a
department list cannot remove management access; this separation is deliberate and
is recorded in the MOP risk register.
