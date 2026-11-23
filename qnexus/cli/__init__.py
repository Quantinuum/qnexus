"""CLI for qnexus."""

import click

from .auth import login, logout
from .check import check
from .compile import compile
from .devices import devices
from .jobs import jobs
from .submit import submit


@click.group()
def entrypoint() -> None:
    """Quantinuum Nexus API client."""


entrypoint.add_command(jobs)
entrypoint.add_command(login)
entrypoint.add_command(logout)
entrypoint.add_command(submit)
entrypoint.add_command(compile)
entrypoint.add_command(check)
entrypoint.add_command(devices)
