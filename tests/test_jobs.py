"""Tests related to running jobs."""

import uuid
from datetime import datetime
from unittest import mock

import pytest
from quantinuum_schemas.models.backend_config import SeleneConfig

import qnexus as qnx
from qnexus.context import using_target_region
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


def test_target_region_from_context_is_used_for_execute_submission() -> None:
    """`using_target_region` should inject target_region into execute job submissions."""

    my_proj = ProjectRef(
        id=uuid.uuid4(), annotations=Annotations(), contents_modified=datetime.now()
    )

    hugr_ref = HUGRRef(
        id=uuid.uuid4(),
        annotations=Annotations(),
        project=my_proj,
    )

    with mock.patch("qnexus.client.jobs._execute.get_nexus_client") as gnc:
        mock_client = mock.MagicMock()

        mock_resp = mock.MagicMock()
        mock_resp.status_code = 202
        mock_resp.json.return_value = {
            "data": {
                "id": str(uuid.uuid4()),
                "attributes": {
                    "name": "execute job",
                    "timestamps": {
                        "created": datetime.now().isoformat(),
                        "modified": datetime.now().isoformat(),
                    },
                    "status": {
                        "status": "COMPLETED",
                        "message": "The job is completed.",
                        "completed_time": "2026-02-27T09:11:14.478969+00:00",
                        "queued_time": "2026-02-27T09:11:14.398557+00:00",
                        "submitted_time": "2026-02-27T09:11:03.491972+00:00",
                    },
                },
            }
        }

        mock_client.post.return_value = mock_resp
        gnc.return_value = mock_client

        with using_target_region("sg"):
            qnx.start_execute_job(
                programs=[hugr_ref],
                n_shots=[10],
                backend_config=SeleneConfig(),
                project=my_proj,
                name="region test",
            )

        payload = mock_client.post.call_args.kwargs["json"]
        assert payload["data"]["attributes"]["definition"]["target_region"] == "sg"


def test_explicit_target_region_overrides_context() -> None:
    """An explicit `target_region` kwarg should take precedence over the context value."""

    my_proj = ProjectRef(
        id=uuid.uuid4(), annotations=Annotations(), contents_modified=datetime.now()
    )

    hugr_ref = HUGRRef(
        id=uuid.uuid4(),
        annotations=Annotations(),
        project=my_proj,
    )

    with mock.patch("qnexus.client.jobs._execute.get_nexus_client") as gnc:
        mock_client = mock.MagicMock()

        mock_resp = mock.MagicMock()
        mock_resp.status_code = 202
        mock_resp.json.return_value = {
            "data": {
                "id": str(uuid.uuid4()),
                "attributes": {
                    "name": "execute job",
                    "timestamps": {
                        "created": datetime.now().isoformat(),
                        "modified": datetime.now().isoformat(),
                    },
                    "status": {
                        "status": "COMPLETED",
                        "message": "The job is completed.",
                        "completed_time": "2026-02-27T09:11:14.478969+00:00",
                        "queued_time": "2026-02-27T09:11:14.398557+00:00",
                        "submitted_time": "2026-02-27T09:11:03.491972+00:00",
                    },
                },
            }
        }

        mock_client.post.return_value = mock_resp
        gnc.return_value = mock_client

        with using_target_region("sg"):
            qnx.start_execute_job(
                programs=[hugr_ref],
                n_shots=[10],
                backend_config=SeleneConfig(),
                project=my_proj,
                name="region override test",
                target_region="us",
            )

        payload = mock_client.post.call_args.kwargs["json"]
        assert payload["data"]["attributes"]["definition"]["target_region"] == "us"
