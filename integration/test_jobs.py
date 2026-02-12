"""Test basic functionality relating to the job module."""

from collections import Counter
from datetime import datetime
from time import sleep
from typing import Any, Callable, ContextManager
from uuid import UUID

import pandas as pd
import pytest
from hugr.package import Package
from pytket.backends.backendinfo import BackendInfo
from pytket.backends.backendresult import BackendResult
from pytket.circuit import Circuit
from quantinuum_schemas.models.backend_config import BaseBackendConfig
from quantinuum_schemas.models.hypertket_config import HyperTketConfig

import qnexus as qnx
import qnexus.exceptions as qnx_exc
from qnexus.models.job_status import JobStatusEnum
from qnexus.models.references import (
    CircuitRef,
    CompilationPassRef,
    CompilationResultRef,
    CompileJobRef,
    ExecuteJobRef,
    ExecutionResultRef,
    IncompleteJobItemRef,
    JobRef,
    ProjectRef,
    Ref,
)

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
    global compile_job_name
    global execute_job_name

    project_name = project_name.replace("{test_suite_name}", test_suite_name)
    circuit_name = circuit_name.replace("{test_suite_name}", test_suite_name)
    compile_job_name = compile_job_name.replace("{test_suite_name}", test_suite_name)
    execute_job_name = execute_job_name.replace("{test_suite_name}", test_suite_name)


def test_job_get_all(
    create_compile_job_in_project: Callable[..., ContextManager[CompileJobRef]],
    create_execute_job_in_project: Callable[..., ContextManager[ExecuteJobRef]],
    test_circuit: Circuit,
) -> None:
    """Test that we can get an iterator over all jobs."""

    with create_compile_job_in_project(
        project_name=project_name,
        job_name=compile_job_name,
        circuit=test_circuit,
        circuit_name=circuit_name,
    ):
        with create_execute_job_in_project(
            project_name=project_name,
            job_name=execute_job_name,
            circuit=test_circuit,
            circuit_name=circuit_name,
        ):
            proj_ref = qnx.projects.get(name=project_name)
            my_job_db_matches = qnx.jobs.get_all(project=proj_ref)

            assert isinstance(my_job_db_matches.count(), int)
            assert isinstance(my_job_db_matches.summarize(), pd.DataFrame)

            for job_ref in my_job_db_matches.list():
                assert isinstance(job_ref, JobRef)
                assert job_ref.backend_config is not None
                assert isinstance(job_ref.backend_config, BaseBackendConfig)


def test_job_get_by_id(
    create_compile_job_in_project: Callable[..., ContextManager[CompileJobRef]],
    create_execute_job_in_project: Callable[..., ContextManager[ExecuteJobRef]],
    test_circuit: Circuit,
    test_ref_serialisation: Callable[[str, Ref], None],
) -> None:
    """Test that we can get JobRefs by id and their serialisation."""

    def get_sanitised_job_ref(job_ref: CompileJobRef | ExecuteJobRef) -> dict[str, Any]:
        """Return the model_dump of a JobRef but excluding the fields that is ok if they
        have changed."""
        return job_ref.model_dump(
            exclude={
                "last_message": True,
                "last_status": True,
                "system": True,
                "__all__": {"contents_modified": True, "modified": True},
            }
        )

    with create_compile_job_in_project(
        project_name=project_name,
        job_name=compile_job_name,
        circuit=test_circuit,
        circuit_name=circuit_name,
    ) as compile_job_ref:
        with create_execute_job_in_project(
            project_name=project_name,
            job_name=execute_job_name,
            circuit=test_circuit,
            circuit_name=circuit_name,
        ) as execute_job_ref:
            assert isinstance(compile_job_ref, CompileJobRef)
            assert isinstance(compile_job_ref.backend_config, BaseBackendConfig)

            my_compile_job_by_id = qnx.jobs.get(id=compile_job_ref.id)
            assert isinstance(my_compile_job_by_id, CompileJobRef)

            # Some attributes might have changed, so need to mask them out while comparing
            assert get_sanitised_job_ref(compile_job_ref) == get_sanitised_job_ref(
                my_compile_job_by_id
            )
            test_ref_serialisation("compile", my_compile_job_by_id)

            assert isinstance(execute_job_ref, ExecuteJobRef)
            assert isinstance(execute_job_ref.backend_config, BaseBackendConfig)

            my_execute_job_by_id = qnx.jobs.get(id=execute_job_ref.id)
            assert isinstance(my_execute_job_by_id, ExecuteJobRef)

            # Some attributes might have changed, so need to mask them out while comparing
            assert get_sanitised_job_ref(execute_job_ref) == get_sanitised_job_ref(
                my_execute_job_by_id
            )

            test_ref_serialisation("execute", my_execute_job_by_id)


def test_compile_job_get(
    create_compile_job_in_project: Callable[..., ContextManager[CompileJobRef]],
    test_circuit: Circuit,
) -> None:
    """Test that we can get a specific unique CompileJobRef,
    or get an appropriate exception."""

    with create_compile_job_in_project(
        project_name=project_name,
        job_name=compile_job_name,
        circuit=test_circuit,
        circuit_name=circuit_name,
    ) as compile_job_ref:
        assert isinstance(compile_job_ref, CompileJobRef)
        assert compile_job_ref.last_status_detail is not None

        with pytest.raises(qnx_exc.NoUniqueMatch):
            qnx.jobs.get()

        with pytest.raises(qnx_exc.ZeroMatches):
            qnx.jobs.get(name=f"{datetime.now()}_{datetime.now()}")


def test_execute_job_get(
    create_execute_job_in_project: Callable[..., ContextManager[ExecuteJobRef]],
    test_circuit: Circuit,
) -> None:
    """Test that we can get a specific unique ExecuteJobRef,
    or get an appropriate exception."""
    with create_execute_job_in_project(
        project_name=project_name,
        job_name=execute_job_name,
        circuit=test_circuit,
        circuit_name=circuit_name,
    ) as execute_job_ref:
        assert isinstance(execute_job_ref, ExecuteJobRef)
        assert execute_job_ref.last_status_detail is not None

        with pytest.raises(qnx_exc.NoUniqueMatch):
            qnx.jobs.get()

        with pytest.raises(qnx_exc.ZeroMatches):
            qnx.jobs.get(name=f"{datetime.now()}_{datetime.now()}")


def test_submit_compile(
    create_compile_job_in_project: Callable[..., ContextManager[CompileJobRef]],
    test_circuit: Circuit,
    test_ref_serialisation: Callable[[str, Ref], None],
) -> None:
    """Test that we can run a compile job in Nexus, wait for the job to complete and
    obtain the results from the compilation."""
    config = qnx.AerConfig()

    with create_compile_job_in_project(
        project_name=project_name,
        job_name=compile_job_name,
        circuit=test_circuit,
        circuit_name=circuit_name,
        backend_config=config,
    ) as compile_job_ref:
        assert isinstance(compile_job_ref, CompileJobRef)

        qnx.jobs.wait_for(compile_job_ref)

        compile_results = qnx.jobs.results(compile_job_ref)

        assert len(compile_results) == 1
        compilation_result = compile_results[0]
        assert isinstance(compilation_result, CompilationResultRef)
        test_ref_serialisation("compile_result", compilation_result)

        assert isinstance(compilation_result.get_input(), CircuitRef)
        assert isinstance(compilation_result.get_output(), CircuitRef)

        first_pass_data = compilation_result.get_passes()[0]

        assert isinstance(first_pass_data, CompilationPassRef)
        assert isinstance(first_pass_data.get_input(), CircuitRef)
        assert isinstance(first_pass_data.get_output(), CircuitRef)
        assert isinstance(first_pass_data.pass_name, str)
        test_ref_serialisation("compilation_pass", first_pass_data)

        cj_ref = qnx.jobs.get(id=compile_job_ref.id)
        assert cj_ref.backend_config == config


def test_compile(
    test_case_name: str,
    create_circuit_in_project: Callable[
        [Circuit, str, str], ContextManager[CircuitRef]
    ],
    test_circuit: Circuit,
) -> None:
    """Test that we can run the utility compile function and get compiled circuits."""

    local_project_name = f"project for {test_case_name}"
    local_circuit_name = f"circuit for {test_case_name}"
    local_compile_job_name = f"compile job for {test_case_name}"

    with create_circuit_in_project(
        test_circuit,
        local_project_name,
        local_circuit_name,
    ) as circ_ref:
        my_proj = qnx.projects.get(name=local_project_name)

        compiled_circuits = qnx.compile(
            programs=[circ_ref],
            name=local_compile_job_name,
            project=my_proj,
            backend_config=qnx.AerConfig(),
        )

        assert len(compiled_circuits) == 1
        assert isinstance(compiled_circuits[0], CircuitRef)


def test_get_results_for_incomplete_compile(
    test_case_name: str,
    create_circuit_in_project: Callable[
        [Circuit, str, str], ContextManager[CircuitRef]
    ],
    test_circuit: Circuit,
) -> None:
    """Test that we can run a compile job in Nexus, and fetch complete results for
    an otherwise errored/incomplete job."""

    local_project_name = f"project for {test_case_name}"
    local_circuit_name = f"circuit for {test_case_name}"

    with create_circuit_in_project(
        test_circuit,
        local_project_name,
        local_circuit_name,
    ) as circ_ref:
        proj_ref = qnx.projects.get_or_create(local_project_name)

        # Will create `n_jobs` compile jobs to guarantee that the last job
        # has not completed before checking the incomplete results
        n_jobs = 10
        compile_job_ref = None
        for job_num in range(n_jobs):
            compile_job_name = f"compile job {job_num} for {test_case_name}"

            compile_job_ref = qnx.start_compile_job(
                programs=[circ_ref],
                name=compile_job_name,
                project=proj_ref,
                backend_config=qnx.AerConfig(),
            )
        # check the job while not complete
        assert isinstance(compile_job_ref, CompileJobRef)
        assert qnx.jobs.status(compile_job_ref).status != JobStatusEnum.COMPLETED

        with pytest.raises(qnx_exc.ResourceFetchFailed):
            qnx.jobs.results(compile_job_ref)

        compile_results = qnx.jobs.results(compile_job_ref, allow_incomplete=True)
        assert len(compile_results) == 1
        compile_item = compile_results[0]
        assert isinstance(compile_item, IncompleteJobItemRef)
        assert isinstance(compile_item.job_item_integer_id, int)
        assert compile_item.last_status != JobStatusEnum.COMPLETED

        # check the job after completion
        qnx.jobs.wait_for(compile_job_ref)
        complete_results = qnx.jobs.results(compile_job_ref, allow_incomplete=True)
        assert len(complete_results) == 1
        assert isinstance(complete_results[0], CompilationResultRef)


def test_compile_hypertket(
    test_case_name: str,
    create_circuit_in_project: Callable[
        [Circuit, str, str], ContextManager[CircuitRef]
    ],
    test_circuit: Circuit,
) -> None:
    """Test that we can run compile circuits for hypertket."""

    local_project_name = f"project for {test_case_name}"
    local_circuit_name = f"circuit for {test_case_name}"
    local_job_name = f"hypertket job for {test_case_name}"

    with create_circuit_in_project(
        test_circuit,
        local_project_name,
        local_circuit_name,
    ) as circ_ref:
        my_proj = qnx.projects.get(name=local_project_name)

        compiled_circuits = qnx.compile(
            programs=[circ_ref],
            name=local_job_name,
            project=my_proj,
            backend_config=qnx.QuantinuumConfig(device_name="H1-1LE"),
            hypertket_config=HyperTketConfig(),
        )

        assert len(compiled_circuits) == 1
        assert isinstance(compiled_circuits[0], CircuitRef)


def test_submit_execute(
    create_execute_job_in_project: Callable[..., ContextManager[ExecuteJobRef]],
    test_circuit: Circuit,
    # test_ref_serialisation: Callable[[str, Ref], None],
) -> None:
    """Test that we can run an execute job in Nexus, wait for the job to complete and
    obtain the results from the execution."""
    config = qnx.AerConfig()

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
        assert isinstance(first_result, ExecutionResultRef)
        assert isinstance(first_result.get_input(), CircuitRef)
        assert isinstance(first_result.download_result(), BackendResult)
        assert isinstance(first_result.download_backend_info(), BackendInfo)

        pj_ref = qnx.jobs.get(id=execute_job_ref.id)
        assert pj_ref.backend_config == config
        assert pj_ref.last_status_detail is not None

        # TODO: check why the serialisation round trip fails even when the
        # objects are the same
        # test_ref_serialisation(ref_type="execute_result", ref=first_result)


def test_execute(
    test_case_name: str,
    create_circuit_in_project: Callable[
        [Circuit, str, str], ContextManager[CircuitRef]
    ],
    test_circuit: Circuit,
) -> None:
    """Test that we can run the utility execute function and get the results of the execution."""
    local_project_name = f"project for {test_case_name}"
    local_circuit_name = f"circuit for {test_case_name}"
    local_execute_job_name = f"execute job for {test_case_name}"

    with create_circuit_in_project(
        test_circuit,
        local_project_name,
        local_circuit_name,
    ) as circ_ref:
        my_proj = qnx.projects.get_or_create(local_project_name)

        backend_results = qnx.execute(
            programs=[circ_ref],
            name=local_execute_job_name,
            project=my_proj,
            backend_config=qnx.AerConfig(),
            n_shots=[10],
        )

        assert len(backend_results) == 1
        assert isinstance(backend_results[0], BackendResult)
        assert isinstance(backend_results[0].get_counts(), Counter)


def test_get_results_for_incomplete_execute(
    test_case_name: str,
    create_circuit_in_project: Callable[
        [Circuit, str, str], ContextManager[CircuitRef]
    ],
    test_circuit: Circuit,
) -> None:
    """Test that we can run an execute job in Nexus, and fetch complete results for
    an otherwise errored/incomplete job."""

    local_project_name = f"project for {test_case_name}"
    local_circuit_name = f"circuit for {test_case_name}"
    job_name = f"execute job for {test_case_name}"

    with create_circuit_in_project(
        test_circuit,
        local_project_name,
        local_circuit_name,
    ) as circ_ref:
        proj_ref = qnx.projects.get_or_create(local_project_name)

        my_q_systems_circuit = qnx.circuits.upload(
            circuit=Circuit(2, 2).ZZPhase(0.5, 0, 1).measure_all(),
            name="qa_q_systems_circuit",
            project=proj_ref,
        )

        execute_job_ref = qnx.start_execute_job(
            programs=[circ_ref, my_q_systems_circuit],
            name=job_name,
            project=proj_ref,
            backend_config=qnx.QuantinuumConfig(device_name="H1-1LE"),
            n_shots=[10, 10],
        )

        assert isinstance(execute_job_ref, ExecuteJobRef)

        with pytest.raises(qnx_exc.JobError):
            qnx.jobs.wait_for(execute_job_ref)

        with pytest.raises(qnx_exc.ResourceFetchFailed):
            qnx.jobs.results(execute_job_ref)

        incomplete_results = qnx.jobs.results(execute_job_ref, allow_incomplete=True)

        # wait for the ZZPhase circuit execution to complete
        for _ in range(10):
            incomplete_results = qnx.jobs.results(
                execute_job_ref, allow_incomplete=True
            )
            if any(isinstance(r, ExecutionResultRef) for r in incomplete_results):
                break
            sleep(10)

        # we expect the CX circuit to fail on H1-1LE, but the ZZPhase circuit should succeed
        assert len(incomplete_results) == 2
        first_item, second_item = incomplete_results[0], incomplete_results[1]
        assert isinstance(first_item, IncompleteJobItemRef)
        assert first_item.id == UUID(int=0)
        assert isinstance(first_item.job_item_integer_id, int)
        assert first_item.last_status == JobStatusEnum.ERROR

        assert isinstance(second_item, ExecutionResultRef)
        assert isinstance(second_item.get_input(), CircuitRef)
        assert isinstance(second_item.download_result(), BackendResult)
        assert isinstance(second_item.download_backend_info(), BackendInfo)


def test_wait_for_raises_on_job_error(
    test_case_name: str,
    create_circuit_in_project: Callable[
        [Circuit, str, str], ContextManager[CircuitRef]
    ],
    test_circuit: Circuit,
) -> None:
    """Test that if a job errors, the wait_for function raises an Exception."""

    local_project_name = f"project for {test_case_name}"
    local_circuit_name = f"circuit for {test_case_name}"
    job_name = f"execute job for {test_case_name}"

    with create_circuit_in_project(
        test_circuit,
        local_project_name,
        local_circuit_name,
    ) as circ_ref:
        proj_ref = qnx.projects.get_or_create(local_project_name)

        # Circuit not compiled for H1-1LE, so we expect it to error when executed
        failing_job_ref = qnx.start_execute_job(
            programs=[circ_ref],
            name=job_name,
            project=proj_ref,
            n_shots=[10],
            backend_config=qnx.QuantinuumConfig(device_name="H1-1LE"),
        )

        with pytest.raises(qnx_exc.ResourceFetchFailed):
            qnx.jobs.results(failing_job_ref)

        with pytest.raises(qnx_exc.JobError):
            qnx.jobs.wait_for(failing_job_ref)


def test_results_not_available_error(
    test_case_name: str,
    create_circuit_in_project: Callable[
        [Circuit, str, str], ContextManager[CircuitRef]
    ],
    test_circuit: Circuit,
) -> None:
    """Test that we can't get the results of a job until it is complete."""

    local_project_name = f"project for {test_case_name}"
    local_circuit_name = f"circuit for {test_case_name}"
    job_name = f"execute job for {test_case_name}"

    with create_circuit_in_project(
        test_circuit,
        local_project_name,
        local_circuit_name,
    ) as circ_ref:
        proj_ref = qnx.projects.get_or_create(local_project_name)

        execute_job_ref = qnx.start_execute_job(
            programs=[circ_ref],
            name=job_name,
            project=proj_ref,
            backend_config=qnx.AerConfig(),
            n_shots=[10],
        )

        with pytest.raises(qnx_exc.ResourceFetchFailed):
            qnx.jobs.results(execute_job_ref)

        qnx.jobs.wait_for(execute_job_ref)

        execute_results = qnx.jobs.results(execute_job_ref)

        assert len(execute_results) == 1
        execution_result = execute_results[0]
        assert isinstance(execution_result, ExecutionResultRef)
        assert isinstance(execution_result.get_input(), CircuitRef)

        assert isinstance(execution_result.download_result(), BackendResult)

        assert isinstance(execution_result.download_backend_info(), BackendInfo)


def test_submit_under_user_group(
    test_case_name: str,
    create_circuit_in_project: Callable[
        [Circuit, str, str], ContextManager[CircuitRef]
    ],
    test_circuit: Circuit,
) -> None:
    """Test that a user can submit jobs under a user_group that
    they belong to.

    Requires that the test user is a member of a group called:
    'QA_IntegrationTestGroup',
    and not a member of a group called:
    'made_up_group'.
    """

    local_project_name = f"project for {test_case_name}"
    local_circuit_name = f"circuit for {test_case_name}"
    correct_group = "QA_IntegrationTestGroup"
    fake_group = "made_up_group"

    with create_circuit_in_project(
        test_circuit,
        local_project_name,
        local_circuit_name,
    ) as circ_ref:
        my_proj = qnx.projects.get_or_create(local_project_name)

        with pytest.raises(qnx_exc.ResourceCreateFailed) as exc:
            qnx.start_compile_job(
                programs=[circ_ref],
                name=f"compile job xfail for {test_case_name}",
                project=my_proj,
                backend_config=qnx.AerConfig(),
                user_group=fake_group,
            )
            assert (
                exc.value.message
                == f"Not a member of any group with name: {fake_group}"
            )

        qnx.start_compile_job(
            programs=[circ_ref],
            name=f"compile job for {test_case_name}",
            project=my_proj,
            backend_config=qnx.AerConfig(),
            user_group=correct_group,
        )

        with pytest.raises(qnx_exc.ResourceCreateFailed):
            qnx.start_execute_job(
                programs=[circ_ref],
                name=f"execute job xfail for {test_case_name}",
                project=my_proj,
                backend_config=qnx.AerConfig(),
                n_shots=[10],
                user_group=fake_group,
            )
            assert (
                exc.value.message
                == f"Not a member of any group with name: {fake_group}"
            )

        qnx.start_execute_job(
            programs=[circ_ref],
            name=f"execute job for {test_case_name}",
            project=my_proj,
            backend_config=qnx.AerConfig(),
            n_shots=[10],
            user_group=correct_group,
        )


def test_job_cost(
    test_case_name: str,
) -> None:
    """Test that we can run an execute job on a device that reports cost,
    and that the cost is available in the JobRef and the ExecutionResultRef."""

    local_project_name = f"project for {test_case_name}"
    job_name = f"execute job for {test_case_name}"

    proj_ref = qnx.projects.get_or_create(local_project_name)

    my_q_systems_circuit = qnx.circuits.upload(
        circuit=Circuit(2, 2).ZZPhase(0.5, 0, 1).measure_all(),
        name="qa_q_systems_circuit",
        project=proj_ref,
    )

    execute_job_ref = qnx.start_execute_job(
        programs=[my_q_systems_circuit],
        name=job_name,
        project=proj_ref,
        backend_config=qnx.QuantinuumConfig(device_name="H2-1SC"),
        n_shots=[10],
    )

    assert isinstance(execute_job_ref, ExecuteJobRef)

    qnx.jobs.wait_for(execute_job_ref)

    job_ref = qnx.jobs.get(id=execute_job_ref.id)
    assert job_ref.last_status_detail is not None
    assert job_ref.last_status_detail.cost is not None

    results = qnx.jobs.results(execute_job_ref)
    assert len(results) == 1
    result_ref = results[0]
    assert isinstance(result_ref, ExecutionResultRef)
    assert result_ref.cost is not None


def test_job_cost_confidence(
    test_case_name: str,
    create_project: Callable[[str], ContextManager[ProjectRef]],
    qa_hugr_package: Package,
) -> None:
    """Test the cost confidence of a Hugr program on a cost checking device,
    and that the cost confidence is available using jobs.cost_confidence()."""

    with create_project(f"project for {test_case_name}") as project_ref:
        hugr_ref = qnx.hugr.upload(
            hugr_package=qa_hugr_package,
            name=f"hugr for {test_case_name}",
            project=project_ref,
        )

        # Check that we can get a cost confidence estimate (using Helios-1SC)
        execute_job_ref = qnx.start_execute_job(
            programs=[hugr_ref],
            n_shots=[10],
            # No other parameters matter for cost estimation, so construct a minimal costing config
            backend_config=qnx.QuantinuumConfig(device_name="Helios-1SC"),
            project=project_ref,
            name="Circuit cost confidence estimation job",
        )

        qnx.jobs.wait_for(execute_job_ref)

        cost_confidence = qnx.jobs.cost_confidence(execute_job_ref)
        assert isinstance(cost_confidence, list)
        assert len(cost_confidence) > 0
