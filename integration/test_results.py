from typing import Callable, ContextManager, cast

import pytest
from constants import JOB_TIMEOUT
from hugr.package import Package
from hugr.qsystem.result import QsysResult
from pytket.backends.backendinfo import BackendInfo
from pytket.backends.backendresult import BackendResult
from pytket.circuit import Circuit
from quantinuum_schemas.models.backend_config import (
    HeliosConfig,
    HeliosEmulatorConfig,
)

import qnexus as qnx
from qnexus.models.references import (
    CircuitRef,
    ExecuteJobRef,
    ExecutionResultRef,
    HUGRRef,
    ProjectRef,
)

backendresult_to_qsysresult = pytest.importorskip(
    "hugr_qir.h_series_helpers.results",
    reason="the optional hugr-qir package is not installed",
).backendresult_to_qsysresult

def test_fetch_qsys_result(
    test_case_name: str,
    create_project: Callable[[str], ContextManager[ProjectRef]],
    qa_hugr_package: Package,
) -> None:
    """Test that we can fetch a qsys result by ID."""
    backend_config = HeliosConfig(
        system_name="Helios-1E-lite",
        emulator_config=HeliosEmulatorConfig(),
    )

    with create_project(f"project for {test_case_name}") as project_ref:
        n_shots = 10

        hugr_ref = qnx.hugr.upload(
            hugr_package=qa_hugr_package,
            name=f"hugr for {test_case_name}",
            project=project_ref,
        )

        job_ref = qnx.start_execute_job(
            programs=[hugr_ref],
            n_shots=[n_shots],
            backend_config=backend_config,
            project=project_ref,
            name=f"selene job for {test_case_name}",
            n_qubits=[5],
            max_cost=[10.0],
        )

        qnx.jobs.wait_for(job_ref, timeout=JOB_TIMEOUT)

        results = qnx.jobs.results(job_ref)

        assert len(results) == 1
        result_ref = results[0]

        assert isinstance(result_ref, ExecutionResultRef)
        assert isinstance(result_ref.download_backend_info(), BackendInfo)
        assert isinstance(result_ref.get_input(), HUGRRef)

        assert result_ref.get_input().id == hugr_ref.id

        direct_fetched_result, _, _ = qnx.results.get(result_ref.id)

        qsys_result = cast(QsysResult, result_ref.download_result())
        assert qsys_result == cast(QsysResult, direct_fetched_result)


# The following global variables and autoused fixture are a
# bit of a hack to have global identifiers for the resources
# used by the `*job_get` tests in this suite. Using the same name for the
# resources means they will be reused if they exist,
# as the "create_*_in_project" fixtures do precisely that.
project_name = "project for {test_suite_name}"
circuit_name = "circuit for {test_suite_name}"
compile_job_name = "compile job for {test_suite_name}"
execute_job_name = "execute job for {test_suite_name}"


@pytest.fixture(autouse=True)
def set_resource_names(test_suite_name: str) -> None:
    global project_name
    global circuit_name
    global execute_job_name

    project_name = project_name.replace("{test_suite_name}", test_suite_name)
    circuit_name = circuit_name.replace("{test_suite_name}", test_suite_name)
    execute_job_name = execute_job_name.replace("{test_suite_name}", test_suite_name)


def test_fetch_pytket_result(
    create_execute_job_in_project: Callable[..., ContextManager[ExecuteJobRef]],
    test_circuit: Circuit,
    # test_ref_serialisation: Callable[[str, Ref], None],
) -> None:
    """Test that we can run an execute job in Nexus, wait for the job to complete and
    obtain the results from the execution."""

    with create_execute_job_in_project(
        project_name=project_name,
        job_name=execute_job_name,
        circuit=test_circuit,
        circuit_name=circuit_name,
    ) as execute_job_ref:
        qnx.jobs.wait_for(execute_job_ref, timeout=JOB_TIMEOUT)

        execute_results = qnx.jobs.results(execute_job_ref)

        assert len(execute_results) == 1

        first_result = execute_results[0]
        direct_fetched_result, _, _ = qnx.results.get(first_result.id)
        assert isinstance(first_result, ExecutionResultRef)
        assert isinstance(first_result.get_input(), CircuitRef)
        downloaded_result = first_result.download_result()

        assert cast(BackendResult, downloaded_result) == cast(
            BackendResult, direct_fetched_result
        )

def test_qir_qsysresult() -> None:


##### GUPPY PROGRAM:

from typing import no_type_check

from guppylang import guppy

import sys
from typing import no_type_check


from guppylang import array, qubit, guppy
from guppylang.std.num import nat
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


#### workflow for submission with qnexus:


import datetime
import qnexus as qnx  # type: ignore
from qnexus.exceptions import AuthenticationError  # type: ignore [import-not-found]
from typing import no_type_check
from guppylang import guppy, qubit
from guppylang.std.builtins import output
from guppylang.std.quantum import measure, x
from hugr_qir.hugr_to_qir import hugr_to_qir
from hugr_qir.output import OutputFormat
from hugr_qir.h_series_helpers.results import backendresult_to_qsysresult

# Generate QIR
hugr_package = main.compile()
qir_bitcode = hugr_to_qir(hugr_package, validate_qir=True, output_format=OutputFormat.BITCODE)

# Get or create a Nexus project to submit jobs in
try:
    project = qnx.projects.get_or_create(name="HUGR-QIR-Demo")
except AuthenticationError:
    qnx.login()
    project = qnx.projects.get_or_create(name="HUGR-QIR-Demo")
qnx.context.set_active_project(project)

# Run job on Nexus
# Use the H2-1 syntax checker (emits dummy results)
# Switch to H2-1E or H2-2E for actual emulation
device_name = "H2-1SC"
qir_name = "HUGR-QIR"
jobname_suffix = datetime.datetime.now().strftime("%Y_%m_%d-%H-%M-%S")
job_name = f"execution-job-qir-{qir_name}-{device_name}-{jobname_suffix}"
qir_program_ref = qnx.qir.upload(qir=qir_bitcode, name=qir_name, project=project)
config = qnx.QuantinuumConfig(device_name=device_name)
ref_execute_job = qnx.start_execute_job(
    programs=[qir_program_ref],
    n_shots=[10],
    backend_config=config,
    name=job_name,
)
qnx.jobs.wait_for(ref_execute_job)
qir_result = qnx.jobs.results(ref_execute_job)[0].download_result()

# Convert Pytket BackendResult to QSysResult
qsysres = backendresult_to_qsysresult(qir_result)

# Print QSysResult
for i, shot in enumerate(qsysres.results):
    print(f"{i}: {shot.entries}")



### CONVERSION and CHECK:


# Convert Pytket BackendResult to QSysResult

qsysres = backendresult_to_qsysresult(qir_result)



# snapshot test?


# Test on the result:


    for i in range(EXPECTED_SHOTS):
        assert len(qsysres[i]) == 3

        set_reg = set()

        for x in qsysres[i]:  # check if reg names are in new qsys result
            set_reg.add(x[0])

        assert set_reg == {"bool", "int", "uint", "bool_array", "int_array"}

        for x in qsysres[i]:
            if x[0] == "bool":
                assert type(x[1]) is bool
            elif x[0] == "int":          
                assert type(x[1]) is int
                assert x[1] == -14
            #elif x[0] == "uint":  # guppy cannot currently generate uint          
            #    assert type(x[1]) is int
            #    assert x[1] == 14
            elif x[0] == "bool_array":
                assert type(x[1]) is list
                assert x[1] == [True, False]
                for y in x[1]:
                    assert type(y) is bool
            elif x[0] == "int_array":
                assert type(x[1]) is list
                assert x[1] == [-1, 0, 1]
                for y in x[1]:
                    assert type(y) is int
            #elif x[0] == "uint_array":  # guppy cannot currently generate uint
            #    assert type(x[1]) is list
            #    assert x[1] == [-1, 0, 1]
            #    for y in x[1]:
            #        assert type(y) is int

                    

    if not skip_snapshot_checks:
        snapshot.assert_match(
            _qs_to_str(qs),
            "test_backend_array.txt",
        )



