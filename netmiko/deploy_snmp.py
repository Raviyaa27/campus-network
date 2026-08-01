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
    python3 deploy_snmp.py                      # every device in the inventory
    python3 deploy_snmp.py --role core_switch   # only devices with that role
    python3 deploy_snmp.py --device SW-CORE-1   # named devices only

    NET_PASSWORD may be set in the environment to avoid the password prompt.

The filters exist because the emulated estate cannot always run every device at
once. Deploying to a subset and repeating for the rest reaches the same end
state, which is a property of the script being idempotent.
"""

from __future__ import annotations

import argparse
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


def current_snmp_config(connection, read_timeout: int) -> list[str]:
    """Return the SNMP lines currently present in the running configuration.

    read_timeout is passed explicitly rather than left at the Netmiko default,
    which assumes a device that answers in milliseconds.
    """
    output = connection.send_command(
        "show running-config | include ^snmp-server",
        read_timeout=read_timeout,
    )
    return [line.strip() for line in output.splitlines() if line.strip()]


def needs_change(current: list[str], intended: list[str]) -> list[str]:
    """Return the intended lines that are not already present on the device.

    This comparison is what makes the script idempotent. Pushing configuration
    unconditionally would also produce a correct device, but every run would
    report a change and the script could not be used to verify that an estate
    is already in its intended state.
    """
    return [line for line in intended if line not in current]


def configure_device(
    device: dict, password: str, intended: list[str], timeouts: dict
) -> str:
    """Apply the SNMP configuration to one device.

    Returns one of CHANGED, UNCHANGED or FAILED for the run summary.
    """
    name = device["name"]
    read_timeout = timeouts["read_timeout"]

    connection = connect(
        device,
        password,
        attempts=timeouts["connect_attempts"],
        retry_delay=timeouts["retry_delay"],
    )
    if connection is None:
        return "FAILED"

    try:
        current = current_snmp_config(connection, read_timeout)
        missing = needs_change(current, intended)

        if not missing:
            logging.info("[%s] SNMP already correct, no change made", name)
            return "UNCHANGED"

        logging.info("[%s] applying %d SNMP line(s)", name, len(missing))
        for line in missing:
            logging.info("[%s]   + %s", name, line)

        # cmd_verify is disabled because it makes Netmiko wait for each command
        # to be echoed back before sending the next. On an emulated device that
        # echo can take seconds, and the wait provides no benefit here since the
        # result is verified by re-reading the configuration on the next run.
        #
        # exit_config_mode is also disabled, and the exit is issued separately
        # below. Netmiko's own exit_config_mode() does not accept the read
        # timeout passed to this call and falls back to a much shorter internal
        # default, which these devices regularly exceed. A timeout at that point
        # would abandon a change that had in fact already been applied.
        connection.send_config_set(
            missing,
            read_timeout=read_timeout,
            cmd_verify=False,
            exit_config_mode=False,
        )

        # Leaving configuration mode and writing to startup are issued as plain
        # commands so that the read timeout applies to them as well.
        connection.send_command("end", expect_string=r"#", read_timeout=read_timeout)
        connection.send_command(
            "write memory", expect_string=r"#", read_timeout=read_timeout
        )
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


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Deploy SNMPv2c configuration to the campus network."
    )
    parser.add_argument(
        "--role",
        action="append",
        help="Only devices with this role. May be given more than once.",
    )
    parser.add_argument(
        "--device",
        action="append",
        help="Only this device by name. May be given more than once.",
    )
    return parser.parse_args()


def select_devices(devices: list[dict], args: argparse.Namespace) -> list[dict]:
    """Apply the command line filters to the inventory."""
    selected = devices

    if args.role:
        selected = [d for d in selected if d.get("role") in args.role]
    if args.device:
        selected = [d for d in selected if d["name"] in args.device]

    return selected


def main() -> int:
    args = parse_arguments()
    setup_logging("deploy-snmp")

    inventory = load_inventory()
    devices = select_devices(inventory["devices"], args)
    intended = build_snmp_commands(inventory["snmp"])
    timeouts = inventory["timeouts"]

    if not devices:
        logging.error("No devices matched the given filters")
        return 1

    logging.info("Deploying SNMPv2c to %d device(s)", len(devices))
    logging.info("Trap destination: %s", inventory["snmp"]["trap_host"])

    password = get_password()

    results = {}
    for device in devices:
        results[device["name"]] = configure_device(
            device, password, intended, timeouts
        )

    return summarise(results)


if __name__ == "__main__":
    sys.exit(main())
