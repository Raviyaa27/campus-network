#!/usr/bin/env python3
"""Configure R-CORE and R-EDGE from the intended state held in routers.yaml.

This script builds both routers from nothing: interface addressing, OSPF, the
NAT rules and the access list that decides which departments reach the
internet. Running it against a wiped router restores that router to service.

The intended configuration is data, not code. routers.yaml describes what each
router should contain and how to read the current state of each part; this file
only contains the logic for comparing the two and closing the gap.

Idempotency is per section. Each section is read from the device, compared with
the intended lines, and pushed only if something is missing. A second run over a
correctly configured router therefore reports every section as already present
and changes nothing.

Usage:
    python3 configure_routers.py                 # both routers
    python3 configure_routers.py --device R-EDGE # one router
    python3 configure_routers.py --dry-run       # report differences only

    NET_PASSWORD may be set in the environment to avoid the password prompt.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.common import (  # noqa: E402
    connect,
    get_password,
    load_inventory,
    load_yaml,
    setup_logging,
    summarise,
)

ROUTER_FILE = Path(__file__).resolve().parent / "inventory" / "routers.yaml"


def line_is_present(line: str, current: list[str]) -> bool:
    """Decide whether one intended line is already satisfied on the device.

    Most lines are a straightforward membership test. Negated commands need
    different treatment: IOS does not record "no shutdown" in the running
    configuration, it simply omits "shutdown". Testing for the literal string
    would report the line as missing on every run and the script would never
    settle, so a "no X" line is treated as satisfied when "X" is absent.
    """
    if line.startswith("no "):
        return line[3:].strip() not in current
    return line in current


def read_section(connection, command: str, read_timeout: int) -> list[str]:
    """Return the device's current configuration for one section."""
    output = connection.send_command(command, read_timeout=read_timeout)
    return [line.strip() for line in output.splitlines() if line.strip()]


def section_is_complete(section: dict, current: list[str]) -> bool:
    """True when every intended line of a section is already on the device."""
    return all(line_is_present(line, current) for line in section["lines"])


def apply_section(connection, section: dict, read_timeout: int) -> None:
    """Push one section in full.

    The whole section is sent rather than only the missing lines because the
    first line is usually a context command. Sending "ip address ..." without
    the preceding "interface ..." would apply it in the wrong place, or be
    rejected outright.
    """
    connection.send_config_set(
        section["lines"],
        read_timeout=read_timeout,
        cmd_verify=False,
        exit_config_mode=False,
    )
    connection.send_command("end", expect_string=r"#", read_timeout=read_timeout)


def configure_router(
    device: dict, sections: list[dict], password: str, timeouts: dict, dry_run: bool
) -> str:
    """Bring one router to its intended state.

    Returns CHANGED, UNCHANGED or FAILED for the run summary.
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

    changed = False

    try:
        for section in sections:
            current = read_section(connection, section["check"], read_timeout)

            if section_is_complete(section, current):
                logging.info("[%s] %-28s already correct", name, section["name"])
                continue

            missing = [
                line for line in section["lines"] if not line_is_present(line, current)
            ]
            logging.info(
                "[%s] %-28s %d line(s) missing", name, section["name"], len(missing)
            )
            for line in missing:
                logging.info("[%s]     + %s", name, line)

            if dry_run:
                changed = True
                continue

            apply_section(connection, section, read_timeout)
            changed = True

        if changed and not dry_run:
            connection.send_command(
                "write memory", expect_string=r"#", read_timeout=read_timeout
            )
            logging.info("[%s] configuration saved", name)
            return "CHANGED"

        if changed:
            logging.info("[%s] dry run, no changes applied", name)
            return "CHANGED"

        logging.info("[%s] already in intended state", name)
        return "UNCHANGED"

    except Exception as error:  # noqa: BLE001
        logging.error("[%s] failed while configuring: %s", name, error)
        return "FAILED"

    finally:
        connection.disconnect()
        logging.info("[%s] disconnected", name)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Configure the campus routers from their intended state."
    )
    parser.add_argument(
        "--device",
        action="append",
        help="Only this router by name. May be given more than once.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would change without applying anything.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_arguments()
    setup_logging("configure-routers")

    inventory = load_inventory()
    timeouts = inventory["timeouts"]
    intended = load_yaml(ROUTER_FILE)["routers"]

    # Connection parameters come from the device inventory, the configuration
    # to apply comes from routers.yaml. Matching them by name keeps the two
    # files independent of each other.
    by_name = {device["name"]: device for device in inventory["devices"]}

    targets = []
    for router in intended:
        if args.device and router["name"] not in args.device:
            continue
        if router["name"] not in by_name:
            logging.error("%s is not in the device inventory", router["name"])
            continue
        targets.append((by_name[router["name"]], router["sections"]))

    if not targets:
        logging.error("No routers matched the given filters")
        return 1

    if args.dry_run:
        logging.info("DRY RUN - no configuration will be applied")

    logging.info("Configuring %d router(s)", len(targets))
    password = get_password()

    results = {}
    for device, sections in targets:
        results[device["name"]] = configure_router(
            device, sections, password, timeouts, args.dry_run
        )

    return summarise(results)


if __name__ == "__main__":
    sys.exit(main())
