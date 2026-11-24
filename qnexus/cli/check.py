"""CLI for qnexus."""

import importlib.util
import sys

import click
from watchfiles import watch as watch_files


def get_file_contents(file: str):
    spec = importlib.util.spec_from_file_location("module.name", file)
    foo = importlib.util.module_from_spec(spec)
    sys.modules["module.name"] = foo
    spec.loader.exec_module(foo)
    return foo


@click.command()
@click.argument("guppy_filename")
@click.option("--watch", flag_value=True, default=False)
def check(guppy_filename: str, watch: bool) -> None:
    """Compile a program to HUGR"""

    def check_file(file: str):
        out = _check(file)
        if out is None:
            click.echo("✅ No errors found.")
        else:
            click.echo(out)

    if watch:
        check_file(guppy_filename)
        click.echo("Waiting for changes...")
        for _ in watch_files(guppy_filename):
            check_file(guppy_filename)

    else:
        check_file(guppy_filename)


def _check(input: str) -> list[bytes]:
    """Compile a program to HUGR"""
    try:
        contents = get_file_contents(input)

        if contents.main is None:
            raise Exception("No main function found.")
        program = contents.main
        program.check()
    except Exception as e:
        return e
