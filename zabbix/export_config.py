#!/usr/bin/env python3
"""Export the Zabbix configuration to JSON files for submission.

Zabbix 6.0 offers no user interface export for global dashboards or maps, and
the host export is buried behind a multi step selection. This script performs
all of it through the API in one pass, so the submitted artefacts can be
regenerated exactly rather than assembled by hand.

Produces, in the current directory:

    zabbix_hosts_export.json      the eleven monitored devices, with their SNMP
                                  interfaces, template links and the triggers
                                  defined for this project
    zabbix_map_export.json        the campus topology map
    zabbix_dashboard_export.json  the FoE-UoR Network dashboard

Run on VM-ZABBIX:

    python3 export_config.py

The Zabbix password is prompted for and never stored. Only the standard
library is used, so nothing needs installing on a host with no internet access.
"""

import getpass
import json
import urllib.request

API_URL = "http://localhost/zabbix/api_jsonrpc.php"
HOST_GROUP = "Campus Network"
DASHBOARD_NAME = "FoE-UoR Network"


def call(method: str, params, auth: str | None = None):
    """Make one JSON-RPC call and return its result, or raise on error."""
    payload = {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
    if auth:
        payload["auth"] = auth

    request = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json-rpc"},
    )
    response = json.load(urllib.request.urlopen(request))

    if "error" in response:
        raise SystemExit(f"API error on {method}: {response['error']}")
    return response["result"]


def write(filename: str, data) -> None:
    """Write one export file and report what it contains."""
    text = data if isinstance(data, str) else json.dumps(data, indent=4)
    with open(filename, "w", encoding="utf-8") as handle:
        handle.write(text)
    print(f"  wrote {filename} ({len(text)} bytes)")


def main() -> None:
    password = getpass.getpass("Zabbix Admin password: ")
    token = call("user.login", {"username": "Admin", "password": password})
    print("Authenticated.")

    # Hosts, resolved from the group name rather than hard coded IDs, so the
    # script keeps working if devices are added or the estate is rebuilt.
    groups = call("hostgroup.get", {"filter": {"name": HOST_GROUP}}, token)
    if not groups:
        raise SystemExit(f"Host group '{HOST_GROUP}' not found")

    hosts = call(
        "host.get",
        {"output": ["hostid", "host"], "groupids": groups[0]["groupid"]},
        token,
    )
    print(f"Exporting {len(hosts)} host(s) from '{HOST_GROUP}'")

    write(
        "zabbix_hosts_export.json",
        call(
            "configuration.export",
            {
                "format": "json",
                "options": {"hosts": [h["hostid"] for h in hosts]},
            },
            token,
        ),
    )

    # Maps are exported through the same mechanism.
    maps = call("map.get", {"output": ["sysmapid", "name"]}, token)
    if maps:
        write(
            "zabbix_map_export.json",
            call(
                "configuration.export",
                {
                    "format": "json",
                    "options": {"maps": [m["sysmapid"] for m in maps]},
                },
                token,
            ),
        )

    # Dashboards have no configuration.export support in 6.0, so the raw
    # dashboard.get response is the only available representation.
    write(
        "zabbix_dashboard_export.json",
        call(
            "dashboard.get",
            {
                "output": "extend",
                "selectPages": "extend",
                "filter": {"name": DASHBOARD_NAME},
            },
            token,
        ),
    )

    call("user.logout", [], token)
    print("Done.")


if __name__ == "__main__":
    main()
