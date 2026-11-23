"""CLI for qnexus."""

from typing import Any

import click

from qnexus.client.jobs import  get_all



@click.command()
def jobs(**kwargs: Any) -> None:
    """List jobs."""
    click.echo(get_all(**kwargs).df())


