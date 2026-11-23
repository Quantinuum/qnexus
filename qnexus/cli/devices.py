"""CLI for qnexus."""

import click
from halo import Halo
from tabulate import tabulate

import qnexus as qnx

backendConfigMap = {
    "Helios-1": {"type": "Hardware", "getConfig": lambda: qnx.models.HeliosConfig()},
    "Helios-1SC": {
        "type": "Syntax Checker",
        "getConfig": lambda: qnx.models.HeliosEmulatorConfig(),
    },
    "Helios-1E": {
        "type": "Emulator",
        "getConfig": lambda: qnx.models.HeliosEmulatorConfig(),
    },
    "Helios-1E-lite": {
        "type": "Emulator",
        "getConfig": lambda: qnx.models.HeliosEmulatorConfig(),
    },
    "SelenePlus": {
        "type": "Simulator",
        "getConfig": lambda: qnx.models.SelenePlusConfig(),
    },
    "Selene": {"type": "simulator", "getConfig": lambda: qnx.models.SeleneConfig()},
}


@click.command()
def devices() -> None:
    """List available devices"""

    with Halo(text="Fetching devices...", spinner="dots"):
        devices = qnx.devices.get_all()
        tabulated_devices = [
            [
                d.device_name or d.backend_name,
                backendConfigMap[d.device_name or d.backend_name].get("type"),
            ]
            for d in devices
            if backendConfigMap.get(d.device_name or d.backend_name) is not None
        ]
    click.echo("\n")
    click.echo(tabulate(tabulated_devices, headers=["Name", "Type"], tablefmt="presto"))
    click.echo("\n")
