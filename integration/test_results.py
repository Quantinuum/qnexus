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


def test_h2_qsysresult(
    test_case_name: str,
    create_project: Callable[[str], ContextManager[ProjectRef]],
    qa_h2_hugr_qir_package: Package,
) -> None:
    """Test the execution and results conversion of a HUGR program compiled to
    QIR for a H2-generation system."""

    pytest.importorskip(
        "hugr_qir",
        reason="the hugr-qir package is not installed",
    )

    from hugr_qir.hugr_to_qir import hugr_to_qir
    from hugr_qir.output import OutputFormat

    EXPECTED_SHOTS = 10

    with create_project(project_name) as project_ref:
        qir_bitcode = hugr_to_qir(
            qa_h2_hugr_qir_package,
            validate_qir=True,
            output_format=OutputFormat.BITCODE,
        )
        qir_ref = qnx.qir.upload(
            qir=cast(bytes, qir_bitcode),
            name=f"hugr for {test_case_name}",
            project=project_ref,
        )

        ref_execute_job = qnx.start_execute_job(
            programs=[qir_ref],
            n_shots=[EXPECTED_SHOTS],
            backend_config=qnx.QuantinuumConfig(device_name="H2-1SC"),
            name=f"H2-1SC hugr_qir job for {test_case_name}",
            project=project_ref,
        )
        qnx.jobs.wait_for(ref_execute_job, timeout=JOB_TIMEOUT)
        result_ref = cast(ExecutionResultRef, qnx.jobs.results(ref_execute_job)[0])
        qsysres = result_ref.download_h2_qsysresult()

        for i in range(EXPECTED_SHOTS):
            assert len(qsysres[i]) == 4

            set_reg = set()

            for x in qsysres[i]:  # check if reg names are in new qsys result
                set_reg.add(x[0])

            assert set_reg == {"bool", "int", "bool_array", "int_array"}

            # Because we run on H2-1SC results will be all zeros
            for x in qsysres[i]:
                if x[0] == "bool":
                    assert type(x[1]) is bool
                    assert x[1] == False
                elif x[0] == "int":
                    assert type(x[1]) is int
                    assert x[1] == 0
                elif x[0] == "bool_array":
                    assert type(x[1]) is list
                    assert x[1] == [False, False]
                    for y in x[1]:
                        assert type(y) is bool
                elif x[0] == "int_array":
                    assert type(x[1]) is list
                    assert x[1] == [0, 0, 0]
                    for y in x[1]:
                        assert type(y) is int
