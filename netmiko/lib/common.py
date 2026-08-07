"""Shared helpers for the campus network automation scripts.

Everything the individual scripts have in common lives here: reading the
inventory, obtaining credentials without storing them, setting up a timestamped
log file, and opening an SSH session with consistent error handling.

Keeping these in one module means a change to, for example, how credentials are
obtained is made once rather than in every script.
"""

from __future__ import annotations

import getpass
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import yaml
from netmiko import ConnectHandler
from netmiko.exceptions import (
    NetmikoAuthenticationException,
    NetmikoTimeoutException,
)

# Paths are derived from this file's location rather than assumed, so the
# scripts work regardless of the directory they are launched from.
NETMIKO_DIR = Path(__file__).resolve().parent.parent
INVENTORY_FILE = NETMIKO_DIR / "inventory" / "devices.yaml"
LOG_DIR = NETMIKO_DIR / "logs"


def load_yaml(path: Path) -> dict:
    """Read a YAML file, failing with a clear message if it is missing."""
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    with open(path, encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def load_inventory(path: Path = INVENTORY_FILE) -> dict:
    """Read the YAML inventory and merge the defaults into each device.

    Returns the whole inventory document. Each entry under 'devices' is
    returned with the shared 'defaults' already applied, so callers receive
    complete connection parameters and never need to know about defaults.
    """
    inventory = load_yaml(path)

    defaults = inventory.get("defaults", {})
    merged = []
    for device in inventory.get("devices", []):
        # Defaults first so that anything set on the device itself wins.
        merged.append({**defaults, **device})
    inventory["devices"] = merged

    return inventory


def get_password() -> str:
    """Obtain the device password without ever storing it in the repository.

    Read from the NET_PASSWORD environment variable when present, which allows
    unattended runs, and fall back to an interactive prompt otherwise.
    """
    password = os.environ.get("NET_PASSWORD")
    if password:
        return password
    return getpass.getpass("Device password: ")


def setup_logging(script_name: str) -> Path:
    """Configure logging to both the console and a timestamped file.

    A separate file per run means the output of one execution is never
    overwritten by the next, which matters when the log is the evidence that a
    change was applied.
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_file = LOG_DIR / f"{script_name}-{timestamp}.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )

    # Paramiko logs the SSH negotiation and the full IOSv licence banner at
    # INFO level for every device, which buries our own output. Warnings and
    # errors from it are still wanted.
    logging.getLogger("paramiko").setLevel(logging.WARNING)

    logging.info("Log file: %s", log_file)
    return log_file


def connect(device: dict, password: str, attempts: int = 3, retry_delay: int = 10):
    """Open an SSH session to one device, retrying on failure.

    Returns a connected Netmiko object, or None if every attempt failed.
    Returning None rather than raising lets the caller carry on with the
    remaining devices: one unreachable switch should not abandon a run across
    eleven.

    Retries are worthwhile here because these devices are emulated and share a
    small number of virtual CPUs. A device that is simply too busy to complete
    the login sequence on one attempt will often succeed moments later, and
    that is a different situation from a device that is genuinely down.
    """
    name = device["name"]

    # Netmiko only accepts its own parameters, so the inventory's descriptive
    # fields are stripped out here.
    params = {
        key: value
        for key, value in device.items()
        if key not in ("name", "role")
    }
    params["password"] = password
    params["secret"] = password

    for attempt in range(1, attempts + 1):
        try:
            logging.info(
                "[%s] connecting to %s (attempt %d/%d)",
                name, device["host"], attempt, attempts,
            )
            connection = ConnectHandler(**params)
            connection.enable()
            logging.info("[%s] connected", name)
            return connection

        except NetmikoAuthenticationException:
            # Wrong credentials will never succeed on a retry, so stop here
            # rather than locking the account out with repeated attempts.
            logging.error("[%s] authentication failed - check credentials", name)
            return None

        except NetmikoTimeoutException:
            logging.warning("[%s] timed out on attempt %d", name, attempt)

        except Exception as error:  # noqa: BLE001 - report anything unexpected
            logging.warning("[%s] attempt %d failed: %s", name, attempt, error)

        if attempt < attempts:
            logging.info("[%s] retrying in %ds", name, retry_delay)
            time.sleep(retry_delay)

    logging.error("[%s] unreachable after %d attempts", name, attempts)
    return None


def run_command(connection, command: str, read_timeout: int) -> str:
    """Send a command and return its output.

    send_command_timing is used rather than send_command because it reads until
    the device stops producing output, instead of waiting for the command to be
    echoed back and the prompt to reappear in an expected form.

    That distinction matters here. Netmiko's pattern matching is reliable
    against hardware that echoes cleanly, but an emulated device under load
    returns output in fragments, and a broken echo fails the match no matter how
    long the timeout is. Reading until the device falls silent avoids the
    problem entirely.
    """
    return connection.send_command_timing(
        command,
        read_timeout=read_timeout,
        last_read=3.0,
        strip_prompt=True,
        strip_command=True,
    )


def summarise(results: dict) -> int:
    """Print a per-device summary and return a shell exit code.

    Returns 0 when every device succeeded and 1 otherwise, so the script can be
    used in a pipeline or checked by another tool.
    """
    logging.info("-" * 60)
    logging.info("Summary")

    for name, outcome in sorted(results.items()):
        logging.info("  %-14s %s", name, outcome)

    failed = [name for name, outcome in results.items() if outcome == "FAILED"]
    changed = [name for name, outcome in results.items() if outcome == "CHANGED"]

    logging.info("-" * 60)
    logging.info(
        "%d device(s) changed, %d unchanged, %d failed",
        len(changed),
        len(results) - len(changed) - len(failed),
        len(failed),
    )

    return 1 if failed else 0
