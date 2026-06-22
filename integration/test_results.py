from typing import Callable, ContextManager, cast

import pytest
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

        qnx.jobs.wait_for(job_ref)

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
        qnx.jobs.wait_for(execute_job_ref)

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
