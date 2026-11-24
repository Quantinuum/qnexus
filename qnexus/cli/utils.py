"""CLI for qnexus."""

import os
from typing import Any, Callable

from click import Command, Option


def is_documented_by(original: Callable) -> Callable:  # type: ignore
    """Forward the documentation from the underlying client function."""

    def wrapper(target: Callable) -> Callable:  # type: ignore
        target.__doc__ = original.__doc__
        return target

    return wrapper


current_path = os.getcwd()
current_dir = current_path.split(os.sep)[-1]



def add_options_to_command(command: Command, model: Any) -> None:
    """Add click options using fields of a pydantic model."""
    # Annotate command with options from dict
    for field, value in model.model_fields.items():
        command.params.append(
            Option(
                [f"--{field}"],
                help=value.description,
                show_default=True,
                default=value.default,
                multiple=isinstance(value.default, list),
            )
        )
