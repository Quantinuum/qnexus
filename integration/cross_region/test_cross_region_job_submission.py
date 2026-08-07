"""Cross-region job submission tests.

These tests submit jobs from a "home" region (logged in against, e.g. SG)
targeting a different "target" region (e.g. US) via the ``target_region``
kwarg on job submission, and verify that the job completes and its results
can be retrieved.
"""

from typing import Callable, ContextManager, cast

import pytest
from constants import JOB_TIMEOUT
from hugr.package import Package
from hugr.qsystem.result import QsysResult
from pytket.backends.backendinfo import BackendInfo
from pytket.backends.backendresult import BackendResult
from pytket.circuit import Bit, Circuit
from quantinuum_schemas.models.backend_config import (
    AerConfig,
    HeliosConfig,
    HeliosEmulatorConfig,
)
from test_qir import make_qir_bitcode_from_file

import qnexus as qnx
import qnexus.exceptions as qnx_exc
from cross_region.region_devices import load_region_devices
from qnexus.models.references import (
    CircuitRef,
    ExecutionResultRef,
    ProjectRef,
    QIRRef,
    QIRResult,
    ResultVersions,
)
from qnexus.models.region import Region


def test_cross_region_execute_job_hugr_ng(
    test_case_name: str,
    create_project: Callable[[str], ContextManager[ProjectRef]],
    qa_hugr_package: Package,
    target_region: Region,
) -> None:
    """Test the execution of a cross island Hugr program on an NG device"""

    device_name = load_region_devices(target_region)["helios_ng_device"]

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
            backend_config=HeliosConfig(
                system_name=device_name,
                emulator_config=HeliosEmulatorConfig(),
            ),
            project=project_ref,
            name=f"cross-region job for {test_case_name}",
            n_qubits=[5],
            max_cost=[10.0],
            target_region=target_region,
        )

        qnx.jobs.wait_for(job_ref, timeout=JOB_TIMEOUT)

        results = qnx.jobs.results(job_ref)
        assert len(results) == 1
        result_ref = results[0]
        assert isinstance(result_ref, ExecutionResultRef)

        qsys_result = cast(QsysResult, result_ref.download_result())
        assert len(qsys_result.results) == n_shots


def test_cross_region_execute_job_qir_ng(
    test_case_name: str,
    create_qir_in_project: Callable[[str, str, bytes], ContextManager[QIRRef]],
    target_region: Region,
) -> None:
    """Test the execution of a cross island QIR program on an NG device"""

    ng_device_name = load_region_devices(target_region)["helios_ng_device"]

    project_name = f"project for {test_case_name}"
    qir_name = f"qir for {test_case_name}"

    with create_qir_in_project(
        project_name,
        qir_name,
        make_qir_bitcode_from_file("base.ll"),
    ) as qir_ref:
        project_ref = qnx.projects.get(name=project_name)

        job_ref = qnx.start_execute_job(
            programs=[qir_ref],
            n_shots=[10],
            max_cost=[10.0],
            backend_config=qnx.QuantinuumConfig(
                device_name=ng_device_name, compiler_options={"max-qubits": 5}
            ),
            project=project_ref,
            name=f"qir job for {test_case_name}",
            target_region=target_region,
        )

        qnx.jobs.wait_for(job_ref, timeout=JOB_TIMEOUT)

        result_ref = qnx.jobs.results(job_ref)[0]
        assert isinstance(result_ref, ExecutionResultRef)
        results = result_ref.download_result()
        # Assert this is a QIR compliant result
        assert isinstance(results, QIRResult)
        escaped_results = results.results.encode("unicode_escape").decode()
        assert "HEADER\\tschema_id\\tlabeled" in escaped_results
        # Can't assert the value is the same, so just check the output is there
        assert "OUTPUT\\tTUPLE\\t2\\tt0" in escaped_results

        v4_results = result_ref.download_result(version=ResultVersions.RAW)
        # Assert this is in v4 format
        assert isinstance(v4_results, QsysResult)
        assert v4_results.results[0].entries[0][0] == "USER:QIRTUPLE:t0"


def test_cross_region_execute_job_qir_og(
    test_case_name: str,
    create_qir_in_project: Callable[[str, str, bytes], ContextManager[QIRRef]],
    qa_qir_bitcode: bytes,
    target_region: Region,
) -> None:
    """Test the execution of a cross island QIR program on an OG device"""

    project_name = f"project for {test_case_name}"
    qir_name = f"qir for {test_case_name}"

    with create_qir_in_project(
        project_name,
        qir_name,
        qa_qir_bitcode,
    ) as qir_program_ref:
        device_name = load_region_devices(target_region)["og_device"]

        project_ref = qnx.projects.get_or_create(name=project_name)

        qir_program_ref = qnx.qir.get(name=qir_name)

        job_ref = qnx.start_execute_job(
            programs=[qir_program_ref],
            n_shots=[10],
            backend_config=qnx.QuantinuumConfig(device_name=device_name),
            project=project_ref,
            name=f"qir job for {test_case_name}",
            target_region=target_region,
        )

        qnx.jobs.wait_for(job_ref, timeout=JOB_TIMEOUT)

        results = qnx.jobs.results(job_ref)

        assert len(results) == 1
        result_ref = results[0]

        assert isinstance(result_ref, ExecutionResultRef)
        assert isinstance(result_ref.download_backend_info(), BackendInfo)
        assert isinstance(result_ref.get_input(), QIRRef)

        assert result_ref.get_input().id == qir_program_ref.id

        qir_result_ref = qnx.jobs.results(job_ref)[0]

        assert isinstance(qir_result_ref, ExecutionResultRef)
        qir_result = qir_result_ref.download_result()
        assert isinstance(qir_result, BackendResult)
        assert sum(qir_result.get_counts().values()) == 10
        assert qir_result.get_bitlist() == [Bit("c", 2), Bit("c", 1), Bit("c", 0)]


def test_cross_region_execute_job_pytket_og(
    test_case_name: str,
    create_circuit_in_project: Callable[
        [Circuit, str, str], ContextManager[CircuitRef]
    ],
    test_circuit: Circuit,
    target_region: Region,
) -> None:
    """Test the execution of a cross-region pytket circuit on an OG device."""

    project_name = f"project for {test_case_name}"
    circuit_name = f"circuit for {test_case_name}"

    with create_circuit_in_project(
        test_circuit,
        project_name,
        circuit_name,
    ) as circuit_ref:
        device_name = load_region_devices(target_region)["og_device"]

        project_ref = qnx.projects.get_or_create(name=project_name)

        job_ref = qnx.start_execute_job(
            programs=[circuit_ref],
            n_shots=[10],
            backend_config=qnx.QuantinuumConfig(device_name=device_name),
            project=project_ref,
            name=f"pytket job for {test_case_name}",
            target_region=target_region,
        )

        qnx.jobs.wait_for(job_ref, timeout=JOB_TIMEOUT)

        results = qnx.jobs.results(job_ref)
        assert len(results) == 1
        result_ref = results[0]

        assert isinstance(result_ref, ExecutionResultRef)
        assert isinstance(result_ref.download_backend_info(), BackendInfo)
        assert isinstance(result_ref.get_input(), CircuitRef)
        assert result_ref.get_input().id == circuit_ref.id

        pytket_result = result_ref.download_result()
        assert isinstance(pytket_result, BackendResult)
        assert sum(pytket_result.get_counts().values()) == 10


def test_reject_cross_region_job_for_nexus_simulators(
    test_case_name: str,
    create_project: Callable[[str], ContextManager[ProjectRef]],
    create_circuit_in_project: Callable[
        [Circuit, str, str], ContextManager[CircuitRef]
    ],
    qa_hugr_package: Package,
    target_region: Region,
    test_circuit: Circuit,
) -> None:
    """Nexus-hosted simulators (e.g. Aer) cannot be targeted at a region
    other than the one the job is submitted from."""

    local_project_name = f"project for {test_case_name}"
    local_circuit_name = f"circuit for {test_case_name}"

    with create_circuit_in_project(
        test_circuit,
        local_project_name,
        local_circuit_name,
    ) as circ_ref:
        my_proj = qnx.projects.get_or_create(local_project_name)

        with pytest.raises(qnx_exc.ResourceCreateFailed) as exc:
            qnx.start_execute_job(
                programs=[circ_ref],
                n_shots=[10],
                backend_config=AerConfig(),
                project=my_proj,
                name=f"cross-region simulator job for {test_case_name}",
                target_region=target_region,
            )
            assert exc.value.status_code == 400
            assert "Nexus hosted simulators can only be run in the current region" in (
                exc.value.message
            )
