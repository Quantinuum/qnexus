"""CLI for qnexus."""

from typing import Literal

import click
from colorama import Style
from halo import Halo
from tabulate import tabulate

import qnexus as qnx

from .compile import _compile
from .devices import backendConfigMap

# mock project for testing
qnx.context.set_active_project_token(
    qnx.projects.get(id="91199097-4aeb-4d52-9e67-1b6a0c5b0493")
)


@click.command()
@click.argument("input")
@click.option("--name", "--n", default=None, show_default=True, help="Name of the job")
@click.option(
    "--maxcost", "--c", default=10, show_default=True, help="Max cost of the job."
)
@click.option(
    "--shots",
    "--s",
    default=1,
    show_default=True,
    help="Number of times to execute the program.",
)
@click.option(
    "--qubits", "--q", default=8, show_default=True, help="Expected qubit allocation."
)
@click.option("--backend", "--b", default="Selene")
@click.option("--noverify", "--nv", flag_value=True, default=False)
def submit(
    input: str,
    name: str,
    maxcost: int,
    shots: int,
    qubits: int,
    backend: Literal[
        "Helios-1", "Helios-1SC", "Helios-1E", "Helios-1E-lite", "SelenePlus", "Selene"
    ],
    noverify: bool,
) -> None:
    """Run a program"""

    name = name or input

    backendDef = backendConfigMap[backend]
    config = backendDef["getConfig"]()

    current_project = qnx.context.get_active_project()

    if not noverify:
        click.echo("\n")
        click.echo("This will:")
        click.echo(f"1. Compile {input}")
        click.echo(f"2. Upload {input}.hugr to Nexus")
        click.echo("3. Submit the following job to Nexus:")
        click.echo(
            tabulate(
                [
                    [
                        Style.DIM + "Project",
                        Style.NORMAL + current_project.annotations.name,
                    ],
                    [Style.DIM + "Job Name", Style.NORMAL + name],
                    [Style.DIM + "Qubits", Style.NORMAL + str(qubits)],
                    [Style.DIM + "Shots", Style.NORMAL + str(shots)],
                    [
                        Style.DIM + "Device",
                        Style.NORMAL + f"{backend} ({backendDef['type']})",
                    ],
                    [Style.DIM + "Max Cost", Style.NORMAL + f"{maxcost} HQC(s)"],
                ]
            )
        )
        click.confirm("Accept?", abort=True)

    with Halo(spinner="dots"):
        d_bytes = _compile(input)

    with Halo(text="Uploading program...", spinner="dots"):
        hugr_ref = qnx.hugr.upload(hugr_package=d_bytes, name=input)

    with Halo(text="Submitting job...", spinner="dots"):
        job_ref = qnx.start_execute_job(
            name=name,
            programs=[hugr_ref],
            n_shots=[shots],
            n_qubits=qubits,
            max_cost=maxcost,
            backend_config=config,
        )

    click.echo("✅ Job successfully submitted.")
    click.echo(f"🔗 https://nexus.quantinuum.com/jobs/{job_ref.id}")
