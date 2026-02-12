"""Tests related to running jobs against QSys devices."""

from typing import Callable, ContextManager, cast

import pytest
from hugr.package import Package
from hugr.qsystem.result import QsysResult
from pytket.backends.backendinfo import BackendInfo
from quantinuum_schemas.models.backend_config import (
    BackendConfig,
    HeliosConfig,
    HeliosEmulatorConfig,
    SeleneConfig,
)

import qnexus as qnx
from qnexus.models.references import (
    ExecutionResultRef,
    HUGRRef,
    ProjectRef,
    ResultVersions,
)


@pytest.mark.parametrize(
    "backend_config",
    [
        SeleneConfig(
            n_qubits=5,
        ),
        HeliosConfig(
            system_name="Helios-1E-lite",
            emulator_config=HeliosEmulatorConfig(n_qubits=5),
        ),
    ],
)
def test_guppy_execution(
    test_case_name: str,
    create_project: Callable[[str], ContextManager[ProjectRef]],
    backend_config: BackendConfig,
    qa_hugr_package: Package,
) -> None:
    """Test the execution of a guppy program
    on a next-generation QSys device."""

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
        )

        qnx.jobs.wait_for(job_ref)

        results = qnx.jobs.results(job_ref)

        assert len(results) == 1
        result_ref = results[0]

        assert isinstance(result_ref, ExecutionResultRef)
        assert isinstance(result_ref.download_backend_info(), BackendInfo)
        assert isinstance(result_ref.get_input(), HUGRRef)

        assert result_ref.get_input().id == hugr_ref.id

        qsys_result = cast(QsysResult, result_ref.download_result())
        assert len(qsys_result.results) == n_shots
        assert qsys_result.results[0].entries[0][0] == "teleported"
        assert qsys_result.results[0].entries[0][1] == 1

        # check some QsysResults functionality
        assert len(qsys_result.collated_counts().items()) > 0

        # Assert we can get the same result for v4 results
        v4_qsys_result = cast(
            QsysResult, result_ref.download_result(version=ResultVersions.RAW)
        )
        assert len(v4_qsys_result.results) == n_shots
        assert v4_qsys_result.results[0].entries[0][0] == "USER:BOOL:teleported"
        assert v4_qsys_result.results[0].entries[0][1] == 1

        # This doesn't seem to work with v4 results, thinks everything is going to be a bit.
        # assert len(qsys_result.collated_counts().items()) > 0


def test_hugr_costing(
    test_case_name: str,
    create_project: Callable[[str], ContextManager[ProjectRef]],
    qa_hugr_package: Package,
) -> None:
    """Test the costing of a Hugr program on a cost checking device."""

    with create_project(f"project for {test_case_name}") as project_ref:
        hugr_ref = qnx.hugr.upload(
            hugr_package=qa_hugr_package,
            name=f"hugr for {test_case_name}",
            project=project_ref,
        )

        # Check that we can get a cost estimate (using Helios-1SC)
        cost = qnx.hugr.cost(
            programs=[hugr_ref],
            n_shots=[10],
            project=project_ref,
        )
        assert isinstance(cost, float)


def test_hugr_cost_confidence(
    test_case_name: str,
    create_project: Callable[[str], ContextManager[ProjectRef]],
    qa_hugr_package: Package,
) -> None:
    """Test the cost confidence of a Hugr program on a cost checking device."""

    with create_project(f"project for {test_case_name}") as project_ref:
        hugr_ref = qnx.hugr.upload(
            hugr_package=qa_hugr_package,
            name=f"hugr for {test_case_name}",
            project=project_ref,
        )

        # Check that we can get a cost confidence estimate (using Helios-1SC)
        cost_confidence = qnx.hugr.cost_confidence(
            programs=[hugr_ref],
            n_shots=[10],
            project=project_ref,
        )
        assert isinstance(cost_confidence, list)
        assert len(cost_confidence) > 0
