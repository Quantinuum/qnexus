"""Tests that we can use all available backend configs."""

from typing import Callable, ContextManager

from pytket.backends.backendresult import BackendResult
from pytket.circuit import Circuit

import qnexus as qnx
from qnexus.models.job_status import JobStatusEnum
from qnexus.models.references import (
    CompilationResultRef,
    ExecutionResultRef,
    ProjectRef,
)

CONFIGS_REQUIRE_NO_MEASURE = [qnx.AerUnitaryConfig]


def test_basic_backend_config_usage(
    backend_config: qnx.BackendConfig,
    create_project: Callable[[str], ContextManager[ProjectRef]],
    test_case_name: str,
) -> None:
    """Test basic functionality of supported BackendConfigs."""

    with create_project(f"project for {test_case_name}") as project_ref:
        my_circ = Circuit(2, 2).H(0).CX(0, 1)

        if backend_config.__class__ not in CONFIGS_REQUIRE_NO_MEASURE:
            my_circ.measure_all()

        my_circ = qnx.circuits.upload(
            circuit=my_circ,
            name=f"circuit for {test_case_name}",
            description="This can be safely deleted.",
            project=project_ref,
        )

        compile_job_ref = qnx.start_compile_job(
            programs=[my_circ],
            name=f"compile job for {test_case_name}",
            optimisation_level=2,
            backend_config=backend_config,
            project=project_ref,
        )

        qnx.jobs.wait_for(compile_job_ref)

        # Check the backend config as stored in Nexus matches the one specified
        # at job submission
        stored_backend_config = qnx.jobs.get(id=compile_job_ref.id).backend_config

        # NOTE: QuantinuumConfig noisy_simulation flag getting reset in Nexus
        assert backend_config.model_dump(
            exclude={"noisy_simulation", "max_batch_cost"}
        ) == stored_backend_config.model_dump(
            exclude={"noisy_simulation", "max_batch_cost"}
        )
        # NOTE: If we send `max_batch_cost=None` in the backend config,
        #       then the org's value is used. We will only check that the
        #       job's backend config is a float.
        if isinstance(backend_config, qnx.QuantinuumConfig):
            assert isinstance(
                stored_backend_config.model_dump().get("max_batch_cost"), float
            )

        execute_job_ref = qnx.start_execute_job(
            programs=[
                item.get_output()
                for item in qnx.jobs.results(compile_job_ref)
                if isinstance(item, CompilationResultRef)
            ],
            name=f"execute job for {test_case_name}",
            n_shots=[100],
            backend_config=backend_config,
            project=project_ref,
        )

        qnx.jobs.wait_for(execute_job_ref)

        execute_job_result_refs = qnx.jobs.results(execute_job_ref)

        for result_ref in execute_job_result_refs:
            assert isinstance(result_ref, ExecutionResultRef)
            assert isinstance(result_ref.download_result(), BackendResult)
