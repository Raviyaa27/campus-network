# VM-AUTO build notes

VM-AUTO is the automation host. It runs the Netmiko scripts and the Ansible
playbooks, and it is the only host in the management VLAN.

## Network position

A single interface in VLAN 99, connected to SW-A-DIS port Gi2/1.

| Setting | Value |
|---------|-------|
| Address | 10.99.99.100/24 |
| Gateway | 10.99.99.1 (HSRP virtual address on the core pair) |
| VLAN | 99 (MGMT) |

The gateway is the HSRP virtual address rather than either core switch's real
address, so automation reachability survives the loss of either core.

## Internet access

The management VLAN is deliberately excluded from NAT on R-EDGE, in line with the
policy that only VLAN_DEIE and VLAN_DCEE obtain internet egress. VM-AUTO therefore
has no internet access in normal operation.

When package installation or a repository pull is required, the exclusion is lifted
for the duration of the task and then restored:

```
! Enable - on R-EDGE
ip access-list standard NAT_PERMITTED
 permit 10.99.99.0 0.0.0.255

! Restore - on R-EDGE
ip access-list standard NAT_PERMITTED
 no permit 10.99.99.0 0.0.0.255
```

Treating internet access for the management plane as a change to be made and
reverted, rather than a standing permission, keeps the delivered configuration
consistent with the stated policy. Verify the entry is absent with
`show ip access-lists NAT_PERMITTED` before any assessed demonstration.

## Applying the network configuration

With the repository cloned onto VM-AUTO:

```
sudo cp configs/vm-auto/01-campus.yaml /etc/netplan/01-campus.yaml
sudo chmod 600 /etc/netplan/01-campus.yaml
sudo netplan apply
```

Cloud-init must be prevented from managing the network first, otherwise it
overwrites netplan on reboot:

```
echo "network: {config: disabled}" | sudo tee /etc/cloud/cloud.cfg.d/99-disable-network-config.cfg
sudo mv /etc/netplan/50-cloud-init.yaml /etc/netplan/50-cloud-init.yaml.bak
```

The interface name in `01-campus.yaml` assumes `ens33`. Confirm with `ip -br link`
before applying and edit the file if the guest reports a different name.

## Packages

```
sudo apt update
sudo apt install -y git python3-pip
pip3 install -r netmiko/requirements.txt
sudo apt install -y ansible
```
