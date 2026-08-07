# VM-ZABBIX build notes

Zabbix 6.0 LTS on Ubuntu 22.04, monitoring all eleven network devices over
SNMPv2c.

## Network position

Two interfaces, with different purposes.

| Interface | Attachment | Address | Purpose |
|-----------|-----------|---------|---------|
| ens33 | SW-A-DIS Gi2/0, VLAN 40 | 10.10.40.20/24, gateway 10.10.40.1 | SNMP polling of the campus |
| ens37 | VMware NAT | DHCP | Web interface, reachable from the build host |

The second interface exists because the web interface would otherwise be
unreachable. The build host has no route into the simulated campus, and
`ACL_DIS_IN` denies `10.10.40.0/24` to `10.99.99.0/24`, so HTTP replies to a
browser on the management VLAN would be discarded by the campus policy itself.

Separating the monitoring path from the console path is also what production
deployments do: the server polls devices over the network it monitors, and
operators reach its interface out of band, so a fault in the monitored network
does not also remove the ability to see it.

The NAT interface is configured not to install a default route, so all campus
traffic continues to leave through 10.10.40.1 and the second interface carries
only sessions initiated towards it.

The monitoring server sits in the server farm rather than the management VLAN
because it is a server. `ACL_DIS_IN` on the core pair already permits UDP 161
and ICMP from `10.10.40.20` to `10.99.99.0/24` and `10.99.0.0/24`, which is what
allows it to poll devices whose management addresses are outside its own VLAN.
Those four entries were written when the access control policy was designed, in
anticipation of this host.

## Order of work

Install the packages **before** attaching the VM to the topology.

Zabbix server, MySQL and Apache together are several hundred megabytes. Pulling
that through five software-forwarding emulated devices takes hours; over the
host's NAT interface it takes minutes. The same reasoning applied to VM-AUTO and
is recorded in the implementation log.

1. In VMware, set the VM's network adapter to **NAT** and allocate 2.5 GB RAM
2. Start the VM **from VMware Workstation**, not from GNS3
3. Install and configure as below
4. Shut down, attach to the GNS3 topology, set the static address
5. Set `Adapters = 1` on the GNS3 **node**, not the template

Step 5 matters. Node settings are copied from the template when the node is
created and are not updated by later template edits, which cost several hours
on VM-AUTO.

## Package installation

Add the Zabbix 6.0 LTS repository. Check
<https://repo.zabbix.com/zabbix/6.0/ubuntu/pool/main/z/zabbix-release/> for the
current filename if this one is not found:

```
wget https://repo.zabbix.com/zabbix/6.0/ubuntu/pool/main/z/zabbix-release/zabbix-release_6.0-4+ubuntu22.04_all.deb
sudo dpkg -i zabbix-release_6.0-4+ubuntu22.04_all.deb
sudo apt update
```

```
sudo apt install -y zabbix-server-mysql zabbix-frontend-php zabbix-apache-conf \
                    zabbix-sql-scripts zabbix-agent mysql-server
```

## Database

```
sudo systemctl start mysql
sudo mysql -uroot
```

```sql
CREATE DATABASE zabbix CHARACTER SET utf8mb4 COLLATE utf8mb4_bin;
CREATE USER zabbix@localhost IDENTIFIED BY 'ZabbixDB2026';
GRANT ALL PRIVILEGES ON zabbix.* TO zabbix@localhost;
SET GLOBAL log_bin_trust_function_creators = 1;
QUIT;
```

Import the schema. This takes several minutes and produces no output until it
finishes:

```
sudo zcat /usr/share/zabbix-sql-scripts/mysql/server.sql.gz | mysql --default-character-set=utf8mb4 -uzabbix -p zabbix
```

Then revoke the temporary privilege, which is only needed for the import:

```
sudo mysql -uroot -e "SET GLOBAL log_bin_trust_function_creators = 0;"
```

## Server configuration

Set the database password in `/etc/zabbix/zabbix_server.conf`:

```
DBPassword=ZabbixDB2026
```

Set the timezone in `/etc/zabbix/apache.conf`, in both the PHP 7 and PHP 8
sections:

```
php_value date.timezone Asia/Colombo
```

## Start the services

```
sudo systemctl restart zabbix-server zabbix-agent apache2
sudo systemctl enable zabbix-server zabbix-agent apache2
```

```
sudo systemctl status zabbix-server --no-pager
```

## First login

While still on the NAT interface, browse to `http://<the VM's NAT address>/zabbix`
from the Windows host and complete the setup wizard. Default credentials are
`Admin` / `zabbix`; change the password immediately.

Completing the wizard now, over a fast connection, avoids doing it later through
the emulated network.

## Attaching to the topology

Shut the VM down, then:

1. Add it to the GNS3 topology and cable it to `SW-A-DIS Gi2/0`
2. Set `Adapters = 1` on the node
3. Start it from GNS3
4. Apply the static address below

`/etc/netplan/01-campus.yaml`:

```yaml
network:
  version: 2
  renderer: networkd
  ethernets:
    # Campus interface, managed by GNS3 and cabled to SW-A-DIS Gi2/0.
    ens33:
      dhcp4: false
      addresses: [10.10.40.20/24]
      routes:
        - to: default
          via: 10.10.40.1
      nameservers:
        addresses: [8.8.8.8, 1.1.1.1]

    # Out of band interface on VMware NAT, used only to reach the web
    # interface from the build host. use-routes is disabled so the DHCP
    # supplied default route does not compete with the campus one; without
    # it, SNMP polling could leave through the wrong interface.
    ens37:
      dhcp4: true
      dhcp4-overrides:
        use-routes: false
        use-dns: false
```

Prevent cloud-init from overwriting it, as on VM-AUTO:

```
echo "network: {config: disabled}" | sudo tee /etc/cloud/cloud.cfg.d/99-disable-network-config.cfg
sudo mv /etc/netplan/50-cloud-init.yaml /etc/netplan/50-cloud-init.yaml.bak
sudo chmod 600 /etc/netplan/01-campus.yaml
sudo netplan apply
```

Confirm the interface name with `ip -br link` first and edit the file if the
guest reports something other than `ens33`.

## Verifying it can reach the devices

From VM-ZABBIX, once attached:

```
ping -c 3 10.99.99.2
snmpwalk -v2c -c CampusRO 10.99.99.2 sysName.0
```

`snmpwalk` requires `snmp` to be installed. The community string and trap
destination were pushed to all eleven devices by `netmiko/deploy_snmp.py`, so no
device-side work is needed.

A successful walk returning the device hostname proves the SNMP configuration,
the routing between VLAN 40 and the management VLAN, and the `ACL_DIS_IN`
monitoring entries all work together.
