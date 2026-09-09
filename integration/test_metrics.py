from dataclasses import dataclass
from typing import Callable, ContextManager

from constants import JOB_TIMEOUT
from hugr.package import Package
from hugr.qsystem.result import DataPrimitive, DataValue
from quantinuum_schemas.models.backend_config import (
    HeliosConfig,
    HeliosEmulatorConfig,
)

import qnexus as qnx
from qnexus.models.references import (
    ExecutionResultRef,
    ProjectRef,
    ResultVersions,
)


# Using a dataclass so the assertion error message is more readable
@dataclass
class Comparison:
    predicate: Callable[[DataValue], bool]
    description: str

    def __call__(self, actual: DataValue) -> bool:
        return self.predicate(actual)

    def __str__(self) -> str:
        return self.description


def exact(expected: DataPrimitive) -> Comparison:
    return Comparison(lambda a: a == expected, f"== {expected!r}")


def between(lower: int | float, upper: int | float) -> Comparison:
    return Comparison(
        lambda a: (type(a) is int or type(a) is float) and lower <= a <= upper,
        f"between {lower} and {upper} (inclusive)",
    )


def positive() -> Comparison:
    return Comparison(lambda a: (type(a) is int or type(a) is float) and a > 0, "> 0")


def one_of(*expected: DataPrimitive) -> Comparison:
    return Comparison(lambda a: a in expected, f"one of {list(expected)!r}")


def big_int() -> Comparison:
    return Comparison(lambda a: type(a) is int and a > 1e6, "> 1e6")


# NOTE: These metrics are valid only for the specific guppy program used in the test.
expected_runtime_metrics = [
    {
        "key": "METRICS:BOOL:runtime:METRICS:BOOL:LEAKAGE_REPUMP",
        "comparison": exact(0),
    },
    {
        "key": "METRICS:BOOL:runtime:METRICS:BOOL:RXY_SQUASHING",
        "comparison": exact(1),
    },
    {
        "key": "METRICS:FLOAT:runtime:METRICS:FLOAT:DD_IDLING_THRESHOLD_NS",
        "comparison": exact(0.0),
    },
    {
        "key": "METRICS:FLOAT:runtime:METRICS:FLOAT:RXY_PHI_MEAN",
        "comparison": exact(1.5707963267948966),
    },
    {
        "key": "METRICS:FLOAT:runtime:METRICS:FLOAT:RXY_PHI_VARIANCE",
        "comparison": one_of(2.467401100272339, 2.819886971739816),
    },
    {
        "key": "METRICS:FLOAT:runtime:METRICS:FLOAT:RXY_THETA_MEAN",
        "comparison": one_of(0.8975979010256552, 1.1780972450961724),
    },
    {
        "key": "METRICS:FLOAT:runtime:METRICS:FLOAT:RXY_THETA_VARIANCE",
        "comparison": one_of(2.7191767227491086, 2.9300388065734033),
    },
    {
        "key": "METRICS:FLOAT:runtime:METRICS:FLOAT:RZZ_THETA_MEAN",
        "comparison": exact(1.5707963267948966),
    },
    {
        "key": "METRICS:FLOAT:runtime:METRICS:FLOAT:RZZ_THETA_VARIANCE",
        "comparison": exact(0.0),
    },
    {
        "key": "METRICS:INT:runtime:METRICS:INT:MEASLEAKED_COUNT",
        "comparison": exact(0),
    },
    {
        "key": "METRICS:INT:runtime:METRICS:INT:MEAS_COUNT",
        "comparison": exact(3),
    },
    {
        "key": "METRICS:INT:runtime:METRICS:INT:RXY_COUNT",
        "comparison": one_of(7, 8),  # TODO: confirm RXY_COUNT can differ between shots
    },
    {
        "key": "METRICS:INT:runtime:METRICS:INT:RZZ_COUNT",
        "comparison": exact(2),
    },
    {
        "key": "METRICS:INT:runtime:METRICS:INT:SHOTTIME_NS",
        "comparison": big_int(),
    },
]


def assert_key_and_value_in_raw_collated_shot_results(
    results: dict[str, list[DataPrimitive] | list[DataValue]],
    key: str,
    comparison: Comparison,
) -> None:
    """Helper function to assert expected metrics in RAW results."""
    assert key in results, f"'{key}' expected but not found in RAW results"
    actual = results[key][
        0
    ]  # NOTE: assuming metrics are returned as list of single values
    assert comparison(actual), (
        f"metric '{key}': expected {comparison}, but got {actual!r}"
    )


def test_real_time_metrics(
    test_case_name: str,
    create_project: Callable[[str], ContextManager[ProjectRef]],
    qa_hugr_package: Package,
) -> None:
    """Test that real-time metrics are included in RAW results."""

    qa_hugr_package_n_qubits = 3
    max_cost = 10.0
    n_shots = 10
    device = "Helios-1E"

    backend_config = HeliosConfig(
        system_name=device,
        emulator_config=HeliosEmulatorConfig(),
    )

    with create_project(f"project for {test_case_name}") as project_ref:
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
            name=f"{device} job for {test_case_name}",
            n_qubits=[qa_hugr_package_n_qubits],
            max_cost=[max_cost],
        )

        qnx.jobs.wait_for(job_ref, timeout=JOB_TIMEOUT)

        results = qnx.jobs.results(job_ref)
        result_ref = results[0]
        assert isinstance(result_ref, ExecutionResultRef)
        raw_results = result_ref.download_result(version=ResultVersions.RAW)

        assert len(raw_results.results) == 10
        raw_results_last_shot = raw_results.collated_shots()[-1]

        # Assert shot number and user result tag
        assert_key_and_value_in_raw_collated_shot_results(
            raw_results_last_shot,
            "METRICS:INT:emulator:shot_number",
            exact(n_shots - 1),
        )
        assert_key_and_value_in_raw_collated_shot_results(
            raw_results_last_shot, "USER:BOOL:teleported", one_of(0, 1)
        )

        # Assert expected runtime metrics
        for metric in expected_runtime_metrics:
            assert_key_and_value_in_raw_collated_shot_results(
                raw_results_last_shot, **metric
            )
