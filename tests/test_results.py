"""Tests for results and related fetch error handling."""

import json
import uuid
from datetime import datetime
from typing import Any, Callable
from unittest import mock
import warnings

import pytest

import qnexus.exceptions as qnx_exc
from qnexus.client import circuits, gpu_decoder_configs, hugr, qir, wasm_modules
from qnexus.client import results as results_api
from qnexus.client.jobs import _compile, _execute
from qnexus.client.utils import handle_fetch_errors
from qnexus.models.annotations import Annotations
from qnexus.models.job_status import JobStatusEnum
from qnexus.models.references import (
    CircuitRef,
    CompileJobRef,
    ExecuteJobRef,
    ExecutionResultRef,
    GpuDecoderConfigRef,
    HUGRRef,
    ProjectRef,
    QIRRef,
    ResultType,
    WasmModuleRef,
)


def _project_ref() -> ProjectRef:
    return ProjectRef(
        id=uuid.uuid4(),
        annotations=Annotations(),
        contents_modified=datetime.now(),
    )


def _gone_response() -> mock.MagicMock:
    response = mock.MagicMock()
    response.status_code = 410
    response.text = "gone"
    return response


def test_handle_fetch_errors_maps_410_to_data_gone() -> None:
    response = mock.MagicMock()
    response.status_code = 410
    response.text = "gone"

    with pytest.raises(qnx_exc.DataGone):
        handle_fetch_errors(response)


def _circuit_ref() -> CircuitRef:
    return CircuitRef(
        id=uuid.uuid4(),
        annotations=Annotations(),
        project=_project_ref(),
    )


def _hugr_ref() -> HUGRRef:
    return HUGRRef(
        id=uuid.uuid4(),
        annotations=Annotations(),
        project=_project_ref(),
    )


def _qir_ref() -> QIRRef:
    return QIRRef(
        id=uuid.uuid4(),
        annotations=Annotations(),
        project=_project_ref(),
    )


def _wasm_ref() -> WasmModuleRef:
    return WasmModuleRef(
        id=uuid.uuid4(), annotations=Annotations(), project=_project_ref()
    )


def _gpu_decoder_config_ref() -> GpuDecoderConfigRef:
    return GpuDecoderConfigRef(
        id=uuid.uuid4(), annotations=Annotations(), project=_project_ref()
    )


@pytest.mark.parametrize(
    "fetch_fn,ref_factory",
    [
        (circuits._fetch_circuit, _circuit_ref),
        (hugr._fetch_hugr_bytes, _hugr_ref),
        (qir._fetch_qir, _qir_ref),
        (wasm_modules._fetch_wasm_module, _wasm_ref),
        (gpu_decoder_configs._fetch_gpu_decoder_config, _gpu_decoder_config_ref),
    ],
)
def test_artifact_fetchers_raise_data_gone_on_410(
    fetch_fn: Callable[..., Any],
    ref_factory: Callable[[], Any],
) -> None:
    with mock.patch(f"{fetch_fn.__module__}.get_nexus_client") as get_client:
        client = mock.MagicMock()
        client.get.return_value = _gone_response()
        get_client.return_value = client

        with pytest.raises(qnx_exc.DataGone):
            fetch_fn(ref_factory())


def test_results_get_raises_data_gone_on_410() -> None:
    result_id = uuid.uuid4()

    with mock.patch.object(
        results_api,
        "fetch_pytket_execution_result_by_id",
        side_effect=qnx_exc.ResourceFetchFailed("gone", status_code=410),
    ) as fetch_pytket:
        with mock.patch.object(results_api, "fetch_qsys_result_by_id") as fetch_qsys:
            with pytest.raises(qnx_exc.DataGone):
                results_api.get(result_id)
            fetch_pytket.assert_called_once()
            fetch_qsys.assert_not_called()


def test_compile_results_fetch_raises_data_gone_on_410() -> None:
    compile_job = CompileJobRef(
        id=uuid.uuid4(),
        annotations=Annotations(),
        last_status=JobStatusEnum.SUBMITTED,
        last_message="",
        project=_project_ref(),
    )

    with mock.patch("qnexus.client.jobs._compile.get_nexus_client") as get_client:
        client = mock.MagicMock()
        client.get.return_value = _gone_response()
        get_client.return_value = client

        with pytest.raises(qnx_exc.DataGone):
            _compile._results(compile_job)


def test_execute_results_fetch_raises_data_gone_on_410() -> None:
    execute_job = ExecuteJobRef(
        id=uuid.uuid4(),
        annotations=Annotations(),
        last_status=JobStatusEnum.SUBMITTED,
        last_message="",
        project=_project_ref(),
    )

    with mock.patch("qnexus.client.jobs._execute.get_nexus_client") as get_client:
        client = mock.MagicMock()
        client.get.return_value = _gone_response()
        get_client.return_value = client

        with pytest.raises(qnx_exc.DataGone):
            _execute._results(execute_job)


def test_pytket_results_with_no_snapshot_warn_but_dont_fail() -> None:

    execute_result_ref = ExecutionResultRef(
        id=uuid.uuid4(),
        result_type=ResultType.PYTKET,
        project=_project_ref(),
        annotations=Annotations(),
    )
    mock_response = mock.MagicMock()
    mock_response.status_code = 200
    with open("tests/data/pytket_result_response_no_backend_snapshot.json") as f:
        mock_response.json.return_value = json.load(f)
    with (
        mock.patch("qnexus.client.results.get_nexus_client") as get_client_results,
        mock.patch("qnexus.client.circuits._fetch_by_id") as fetch_circuit,
    ):
        result_client = mock.MagicMock()
        result_client.get.return_value = mock_response
        get_client_results.return_value = result_client

        fetch_circuit.return_value = CircuitRef(
            id=uuid.uuid4(),
            annotations=Annotations(),
            project=ProjectRef(
                id=uuid.uuid4(),
                annotations=Annotations(),
                contents_modified=datetime.now(),
            ),
        )

        with warnings.catch_warnings(record=True) as captured:
            _execute._fetch_pytket_execution_result(execute_result_ref)
        assert len(captured) == 1, captured
        assert captured[0].category is RuntimeWarning
        assert (
            captured[0].message
            == "backend snapshot was expected, but couldn't be found"
        )


def test_qsys_execute_results_with_no_snapshot_warn_but_dont_fail() -> None:
    pass
