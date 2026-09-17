"""Simple guppylang program for testing hugr-qir results conversion."""

from pathlib import Path
from sys import argv

from guppylang import array, guppy, qubit
from guppylang.std.platform import output
from guppylang.std.quantum import measure


@guppy
def main() -> None:
    output("bool", measure(qubit()).read())
    output("int", -14)
    # output("uint", nat(14))  # guppy cannot currently generate uint
    output("bool_array", array(True, False))
    output("int_array", array(-1, 0, 1))
    # output("uint_array", array(nat(0), nat(1), nat(2)))  # guppy cannot currently generate array[nat, n]


main.check()
program = main.compile_function()
# remove the .gpy suffix and add .hugr
Path(argv[0]).with_suffix("").with_suffix(".hugr").write_bytes(program.to_bytes())
