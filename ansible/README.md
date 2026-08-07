# Ansible switch automation

Configures the nine campus switches: the VLAN database, 802.1Q trunks, access
ports and spanning tree. The two routers are managed by the Netmiko scripts in
`../netmiko/`; the reasoning behind that division is in the tool selection
justification.

## First time setup

Install the required collections:

```
ansible-galaxy collection install -r requirements.yml
```

Create the vault holding the device password:

```
cd ansible
ansible-vault create group_vars/all/vault.yml
```

Enter a vault password when prompted, then put a single line in the file:

```yaml
vault_device_password: <the device password>
```

Store the vault password so playbooks do not prompt on every run:

```
echo '<the vault password>' > vault_pass.txt
chmod 600 vault_pass.txt
```

`vault_pass.txt` is excluded by `.gitignore` and must never be committed. The
encrypted `vault.yml` is committed, which is the point of the arrangement: the
credential travels with the project while remaining unreadable without the
vault password.

## Running

```
ansible all -m ping                  reachability check for every switch
ansible-playbook site.yml --check    report differences, change nothing
ansible-playbook site.yml            apply the intended state
```

Limit a run to one group or host when the simulator cannot run the full estate:

```
ansible-playbook site.yml --limit core_switches
ansible-playbook site.yml --limit SW-A-DIS
```

## Layout

| Path | Contents |
|------|----------|
| `inventory/hosts.yml` | Switches grouped by layer |
| `group_vars/all/vars.yml` | Connection settings, references the vault |
| `group_vars/all/vault.yml` | Encrypted device password |
| `group_vars/<group>.yml` | Variables shared by a layer |
| `host_vars/<switch>.yml` | VLANs, trunks and ports for one switch |
| `roles/vlans` | VLAN database |
| `roles/trunking` | 802.1Q trunks, native VLAN, allowed lists |
| `roles/access_ports` | Access VLAN, portfast, BPDU guard |
| `roles/stp` | Spanning tree mode and root placement |
| `site.yml` | Runs the roles in dependency order |
| `playbooks/rollback/` | Returns a switch to a clean baseline |

## Why variables are split the way they are

`group_vars` holds what every member of a layer shares: the core pair carries
all VLANs, distribution switches carry one department plus management.
`host_vars` holds what differs per device: which department VLAN, which ports,
and for the core pair which VLANs it leads in spanning tree.

The split matters for the trunk pruning in particular. Each downlink allows a
different VLAN list, so that list cannot live in a group variable; it is a
property of the individual switch.
