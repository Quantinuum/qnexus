"""Test basic functionality relating to the qir module."""

from collections import Counter
from pathlib import Path
from typing import Callable, ContextManager

import pyqir
from hugr.qsystem.result import QsysResult
from pytket.backends.backendinfo import BackendInfo
from pytket.backends.backendresult import BackendResult
from pytket.circuit import Bit, Circuit
from pytket.qir import pytket_to_qir  # type: ignore[attr-defined]

import qnexus as qnx
from qnexus.models.annotations import PropertiesDict
from qnexus.models.references import (
    ExecutionResultRef,
    ProjectRef,
    QIRRef,
    QIRResult,
    Ref,
    ResultVersions,
)


def test_qir_create_and_update(
    test_case_name: str,
    create_property_in_project: Callable[..., ContextManager[ProjectRef]],
    test_circuit: Circuit,
) -> None:
    """Test that we can create a qir and add a property value."""

    project_name = f"project for {test_case_name}"
    property_name = f"property for {test_case_name}"

    with create_property_in_project(
        project_name=project_name,
        property_name=property_name,
        property_type="string",
        required=False,
    ):
        proj_ref = qnx.projects.get_or_create(project_name)
        qir_name = f"qir for {test_case_name}"

        qir_bitcode = pytket_to_qir(test_circuit, name=qir_name)
        assert isinstance(qir_bitcode, bytes)
        my_new_qir = qnx.qir.upload(qir=qir_bitcode, name=qir_name, project=proj_ref)

        assert isinstance(my_new_qir, QIRRef)

        test_prop_value = "foo"

        updated_qir_ref = qnx.qir.update(
            ref=my_new_qir,
            properties=PropertiesDict({property_name: test_prop_value}),
        )

        assert updated_qir_ref.annotations.properties[property_name] == test_prop_value


def test_qir_download(
    test_case_name: str,
    create_qir_in_project: Callable[[str, str, bytes], ContextManager[QIRRef]],
    qa_qir_bitcode: bytes,
) -> None:
    """Test that QIR bytes can be downloaded from an uploaded QIR module."""

    project_name = f"project for {test_case_name}"
    qir_name = f"qir for {test_case_name}"

    with create_qir_in_project(
        project_name,
        qir_name,
        qa_qir_bitcode,
    ) as qir_ref:
        qir_bytes = qir_ref.download_qir()
        assert isinstance(qir_bytes, bytes)
        assert qir_bytes == qa_qir_bitcode


def test_qir_get_by_id(
    test_case_name: str,
    create_qir_in_project: Callable[[str, str, bytes], ContextManager[QIRRef]],
    qa_qir_bitcode: bytes,
    test_ref_serialisation: Callable[[str, Ref], None],
) -> None:
    """Test that we can get a QIRRef by its ID and its round trip serialisation."""

    project_name = f"project for {test_case_name}"
    qir_name = f"qir for {test_case_name}"

    with create_qir_in_project(
        project_name,
        qir_name,
        qa_qir_bitcode,
    ):
        my_proj = qnx.projects.get(name=project_name)
        my_qir_ref = qnx.qir.get(name=qir_name, project=my_proj)

        qir_ref_by_id = qnx.qir.get(id=my_qir_ref.id)

        assert qir_ref_by_id == my_qir_ref

        test_ref_serialisation("qir", qir_ref_by_id)


def test_qir_get_all(
    test_case_name: str,
    create_qir_in_project: Callable[[str, str, bytes], ContextManager[QIRRef]],
    qa_qir_bitcode: bytes,
) -> None:
    """Test that we can get all qirRefs in a project."""

    project_name = f"project for {test_case_name}"
    qir_name = f"qir for {test_case_name}"

    with create_qir_in_project(
        project_name,
        qir_name,
        qa_qir_bitcode,
    ):
        my_proj = qnx.projects.get(name=project_name)

        qirs = qnx.qir.get_all(project=my_proj)

        assert qirs.count() >= 1
        assert isinstance(qirs.list()[0], QIRRef)


def test_execution(
    test_case_name: str,
    create_qir_in_project: Callable[[str, str, bytes], ContextManager[QIRRef]],
    qa_qir_bitcode: bytes,
) -> None:
    """Test the execution of a QIR program."""

    project_name = f"project for {test_case_name}"
    qir_name = f"qir for {test_case_name}"

    with create_qir_in_project(
        project_name,
        qir_name,
        qa_qir_bitcode,
    ) as qir_program_ref:
        device_name = "H1-1SC"  # Syntax checker - no results

        project_ref = qnx.projects.get_or_create(name=project_name)

        qir_program_ref = qnx.qir.get(name=qir_name)

        job_ref = qnx.start_execute_job(
            programs=[qir_program_ref],
            n_shots=[10],
            backend_config=qnx.QuantinuumConfig(device_name=device_name),
            project=project_ref,
            name=f"qir job for {test_case_name}",
        )

        qnx.jobs.wait_for(job_ref)

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
        assert qir_result.get_counts() == Counter({(0, 0, 0): 10})
        assert qir_result.get_bitlist() == [Bit("c", 2), Bit("c", 1), Bit("c", 0)]


def test_execution_on_NG_devices(
    test_case_name: str,
    create_qir_in_project: Callable[[str, str, bytes], ContextManager[QIRRef]],
) -> None:
    """Test execution on NG devices, specifically to focus on getting the results"""

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
            backend_config=qnx.QuantinuumConfig(
                device_name="Helios-1E", max_cost=10, compiler_options={"max-qubits": 5}
            ),
            project=project_ref,
            name=f"qir job for {test_case_name}",
        )

        qnx.jobs.wait_for(job_ref)

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


def test_costing_qir_on_NG_devices(
    test_case_name: str,
    create_qir_in_project: Callable[[str, str, bytes], ContextManager[QIRRef]],
) -> None:
    """Test the costing of a QIR program on a cost checking device."""

    project_name = f"project for {test_case_name}"
    qir_name = f"qir for {test_case_name}"

    with create_qir_in_project(
        project_name,
        qir_name,
        make_qir_bitcode_from_file("base.ll"),
    ) as qir_ref:
        project_ref = qnx.projects.get(name=project_name)

        # Check that we can get a cost estimate
        cost = qnx.qir.cost(
            programs=[qir_ref],
            n_shots=[10],
            project=project_ref,
        )
        assert isinstance(cost, float)


def test_qir_cost_confidence(
    test_case_name: str,
    create_qir_in_project: Callable[[str, str, bytes], ContextManager[QIRRef]],
) -> None:
    """Test the cost confidence of a QIR program on a cost checking device."""

    project_name = f"project for {test_case_name}"
    qir_name = f"qir for {test_case_name}"

    with create_qir_in_project(
        project_name,
        qir_name,
        make_qir_bitcode_from_file("base.ll"),
    ) as qir_ref:
        project_ref = qnx.projects.get(name=project_name)

        # Check that we can get a cost confidence estimate (using Helios-1SC)
        cost_confidence = qnx.qir.cost_confidence(
            programs=[qir_ref],
            n_shots=[10],
            project=project_ref,
        )
        assert isinstance(cost_confidence, list)
        assert len(cost_confidence) > 0


def make_qir_bitcode_from_file(filename: str) -> bytes:
    with open(
        Path("tests/data").resolve() / filename,
        "r",
    ) as file:
        return pyqir.Module.from_ir(pyqir.Context(), file.read()).bitcode
