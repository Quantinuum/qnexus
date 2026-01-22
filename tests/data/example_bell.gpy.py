"""Simple guppylang program from https://docs.quantinuum.com/guppy"""

from pathlib import Path
from sys import argv

from guppylang import guppy
from guppylang.std.builtins import result
from guppylang.std.quantum import cx, h, measure, qubit, x, z


@guppy
def bell() -> tuple[qubit, qubit]:
    """Constructs a bell state."""
    q1, q2 = qubit(), qubit()
    h(q1)
    cx(q1, q2)
    return q1, q2


@guppy
def main() -> None:
    src = qubit()
    x(src)
    alice, bob = bell()

    cx(src, alice)
    h(src)
    if measure(alice):
        x(bob)
    if measure(src):
        z(bob)

    result("teleported", measure(bob))


main.check()
program = main.compile_function()
# remove the .gpy suffix and add .hugr
Path(argv[0]).with_suffix("").with_suffix(".hugr").write_bytes(program.to_bytes())
