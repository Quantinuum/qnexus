"""Tests related to running jobs."""

import uuid
from datetime import datetime

import pytest
from quantinuum_schemas.models.backend_config import SeleneConfig

import qnexus as qnx
from qnexus.models.annotations import Annotations
from qnexus.models.references import (
    HUGRRef,
    ProjectRef,
)


@pytest.mark.parametrize(
    "n_shots, max_cost, n_qubits, error_param",
    [
        ([10], [10, 20], [5, 10], "n_shots"),
        ([10, 20], [10], [5, 10], "max_cost"),
        ([10, 20], [10, 20], [5], "n_qubits"),
    ],
)
def test_job_parameterization(
    n_shots: list[int],
    max_cost: list[float],
    n_qubits: list[int],
    error_param: str,
) -> None:
    """Test that we can parameterize max_cost and n_qubits for a Hugr program submission."""

    my_proj = ProjectRef(
        id=uuid.uuid4(), annotations=Annotations(), contents_modified=datetime.now()
    )

    hugr_ref = HUGRRef(
        id=uuid.uuid4(),
        annotations=Annotations(),
        project=my_proj,
    )

    with pytest.raises(
        ValueError, match=f"Number of programs must equal number of {error_param}."
    ):
        qnx.start_execute_job(
            programs=[hugr_ref, hugr_ref],
            n_shots=n_shots,
            backend_config=SeleneConfig(),
            project=my_proj,
            name="This job will never run",
            max_cost=max_cost,
            n_qubits=n_qubits,
        )
