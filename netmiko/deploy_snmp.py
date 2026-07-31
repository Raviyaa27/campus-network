#!/usr/bin/env python3
"""Deploy SNMPv2c configuration to every device in the inventory.

Zabbix polls all routers and switches over SNMPv2c, so every device needs the
same community string, trap destination and system identification. Applying
that by hand across eleven devices is slow and easy to get inconsistent, which
is exactly the kind of repetitive, uniform task worth automating.

The script is idempotent: it reads the SNMP configuration already present on
each device and only pushes changes where the running configuration does not
match the intended state. Re-running it against a correctly configured estate
makes no changes and reports every device as unchanged.

Usage:
    python3 deploy_snmp.py

    NET_PASSWORD may be set in the environment to avoid the password prompt.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# Allow the script to import its own lib/ package regardless of where it is run
# from. Without this, running the script from another directory would fail.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.common import (  # noqa: E402
    connect,
    get_password,
    load_inventory,
    setup_logging,
    summarise,
)


def build_snmp_commands(snmp: dict) -> list[str]:
    """Return the SNMP configuration lines intended for every device.

    Built from the inventory rather than written literally here, so the
    community string or trap destination is changed in one place.
    """
    return [
        f"snmp-server community {snmp['community']} {snmp['access']}",
        f"snmp-server host {snmp['trap_host']} version 2c {snmp['community']}",
        f"snmp-server location {snmp['location']}",
        f"snmp-server contact {snmp['contact']}",
        "snmp-server enable traps snmp linkdown linkup coldstart warmstart",
    ]


def current_snmp_config(connection) -> list[str]:
    """Return the SNMP lines currently present in the running configuration."""
    output = connection.send_command("show running-config | include ^snmp-server")
    return [line.strip() for line in output.splitlines() if line.strip()]


def needs_change(current: list[str], intended: list[str]) -> list[str]:
    """Return the intended lines that are not already present on the device.

    This comparison is what makes the script idempotent. Pushing configuration
    unconditionally would also produce a correct device, but every run would
    report a change and the script could not be used to verify that an estate
    is already in its intended state.
    """
    return [line for line in intended if line not in current]


def configure_device(device: dict, password: str, intended: list[str]) -> str:
    """Apply the SNMP configuration to one device.

    Returns one of CHANGED, UNCHANGED or FAILED for the run summary.
    """
    name = device["name"]
    connection = connect(device, password)
    if connection is None:
        return "FAILED"

    try:
        current = current_snmp_config(connection)
        missing = needs_change(current, intended)

        if not missing:
            logging.info("[%s] SNMP already correct, no change made", name)
            return "UNCHANGED"

        logging.info("[%s] applying %d SNMP line(s)", name, len(missing))
        for line in missing:
            logging.info("[%s]   + %s", name, line)

        connection.send_config_set(missing)
        connection.save_config()
        logging.info("[%s] configuration saved", name)
        return "CHANGED"

    except Exception as error:  # noqa: BLE001
        logging.error("[%s] failed while configuring: %s", name, error)
        return "FAILED"

    finally:
        # Always close the session, including when an exception was raised,
        # so devices are not left holding abandoned VTY lines.
        connection.disconnect()
        logging.info("[%s] disconnected", name)


def main() -> int:
    setup_logging("deploy-snmp")

    inventory = load_inventory()
    devices = inventory["devices"]
    intended = build_snmp_commands(inventory["snmp"])

    logging.info("Deploying SNMPv2c to %d device(s)", len(devices))
    logging.info("Trap destination: %s", inventory["snmp"]["trap_host"])

    password = get_password()

    results = {}
    for device in devices:
        results[device["name"]] = configure_device(device, password, intended)

    return summarise(results)


if __name__ == "__main__":
    sys.exit(main())
