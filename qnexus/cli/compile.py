"""CLI for qnexus."""

import importlib.util
import sys

import click


def get_file_contents(file: str):
    spec = importlib.util.spec_from_file_location("module.name", file)
    foo = importlib.util.module_from_spec(spec)
    sys.modules["module.name"] = foo
    spec.loader.exec_module(foo)
    return foo


@click.command()
@click.argument("guppy_filename")
@click.argument("hugr_filename")
@click.option("--watch", default=False)
def compile(guppy_filename: str, hugr_filename: str, watch: bool) -> None:
    """Compile a program to HUGR"""

    content_bytes = _compile(guppy_filename)
    with open(hugr_filename or f"{guppy_filename}.hugr", "wb") as f:
        f.write(content_bytes)
    click.echo(f"HUGR bytes written to {hugr_filename}")


def _compile(input: str) -> list[bytes]:
    """Compile a program to HUGR"""
    click.echo("Compiling program to .hugr...")
    contents = get_file_contents(input)

    if contents.main is None:
        raise Exception("No main function found.")
    program = contents.main
    return program.compile().to_bytes()
