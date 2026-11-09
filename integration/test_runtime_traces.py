"""Tests for downloading runtime traces of jobs run on Helios emulators."""

import time
from typing import Callable, ContextManager
from uuid import uuid4

import pytest
from constants import JOB_TIMEOUT
from hugr.package import Package
from selene_core.trace import Trace
from test_qir import make_qir_bitcode_from_file

import qnexus as qnx
import qnexus.exceptions as qnx_exc
from qnexus.client import get_nexus_client
from qnexus.models.references import (
    HUGRRef,
    ProjectRef,
    QIRRef,
    RuntimeTracesRef,
)

N_SHOTS = 1
TRACE_TIMEOUT_SECONDS = 180
TRACE_POLL_SECONDS = 10

pytestmark = pytest.mark.skip(reason="Runtime traces changes are not in QA env yet.")

def assert_trace_is_valid(trace: Trace) -> None:
    """The trace has events, and every event has a source and a kind."""
    assert isinstance(trace, Trace)
    assert len(trace.events) > 0
    kinds = {record.event.kind for record in trace.events}
    # Every program allocates, measures and resets qubits
    assert {"Gate", "Measurement", "Reset"} <= kinds, f"unexpected kinds: {kinds}"
    assert all(record.source.kind for record in trace.events)


@pytest.mark.parametrize("program_type", ["qir", "hugr"])
def test_download_runtime_trace(
    program_type: str,
    test_case_name: str,
    create_qir_in_project: Callable[[str, str, bytes], ContextManager[QIRRef]],
    create_hugr_in_project: Callable[[str, str, Package], ContextManager[HUGRRef]],
    qa_hugr_package: Package,
    qa_helios_emulator_config: qnx.HeliosConfig
) -> None:
    """A completed job on a Helios emulator has a downloadable runtime trace."""
    project_name = f"project for {test_case_name}"
    program_name = f"{program_type} for {test_case_name}"

    program_context: ContextManager[QIRRef] | ContextManager[HUGRRef]
    if program_type == "qir":
        program_context = create_qir_in_project(
            project_name, program_name, make_qir_bitcode_from_file("base.ll")
        )
    else:
        program_context = create_hugr_in_project(
            project_name, program_name, qa_hugr_package
        )

    with program_context as program_ref:
        job_ref = qnx.start_execute_job(
            programs=[program_ref],
            n_shots=[N_SHOTS],
            max_cost=[10000.0],
            n_qubits=[5],
            backend_config=qa_helios_emulator_config,
            project=qnx.projects.get(name=project_name),
            name=f"{program_type} job for {test_case_name}",
        )
        qnx.jobs.wait_for(job_ref, timeout=JOB_TIMEOUT)

        runtime_traces = qnx.jobs.runtime_traces(job_ref)
        assert len(runtime_traces) == 1
        assert isinstance(runtime_traces[0], RuntimeTracesRef)

        trace = runtime_traces[0].download_runtime_traces()
        assert_trace_is_valid(trace)


def test_download_runtime_trace_of_unknown_item(
    test_case_name: str,
    create_project: Callable[[str], ContextManager[ProjectRef]],
) -> None:
    """Downloading the trace of a job item that does not exist gives a 404."""
    with create_project(f"project for {test_case_name}") as project_ref:
        unknown_id = uuid4()
        trace_ref = RuntimeTracesRef(
            id=unknown_id, job_item_id=unknown_id, project=project_ref
        )

        with pytest.raises(qnx_exc.ResourceFetchFailed) as error:
            trace_ref.download_runtime_traces()
        assert error.value.status_code == 404
