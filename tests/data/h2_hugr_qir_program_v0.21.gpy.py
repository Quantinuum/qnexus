"""Simple guppylang program for testing hugr-qir results conversion."""
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "guppylang ==0.21.6",
# ]
# ///
# mypy: ignore-errors
# pyright: ignore

from pathlib import Path
from sys import argv

from guppylang import array, guppy, qubit
from guppylang.std.platform import result
from guppylang.std.quantum import measure


@guppy
def main() -> None:
    result("bool", measure(qubit()))
    result("int", -14)
    # result("uint", nat(14))  # guppy cannot currently generate uint
    result("bool_array", array(True, False))
    result("int_array", array(-1, 0, 1))
    # result("uint_array", array(nat(0), nat(1), nat(2)))  # guppy cannot currently generate array[nat, n]


main.check()
program = main.compile_function()
# remove the .gpy suffix and add .hugr
Path(argv[0]).with_suffix("").with_suffix(".hugr").write_bytes(program.to_bytes())
