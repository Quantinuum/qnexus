import datetime as dt
import warnings
from typing import Union
from unittest import mock
from uuid import uuid4

from qnexus import QuantinuumConfig
from qnexus.client.jobs._compile import start_compile_job
from qnexus.client.utils import accept_circuits_for_programs
from qnexus.models.references import CircuitRef, ProjectRef

PROJECT_REF = ProjectRef(
    annotations={}, id=uuid4(), contents_modified=dt.datetime.now()
)
CIRCUIT_REF = CircuitRef(
    id=uuid4(),
    annotations={},
    project=PROJECT_REF,
)


def test_wrapper() -> None:
    """
    Test that `accept_circuits_for_programs` decorator invokes the wrapped
    function as expected, emitting a deprecation warning when the old `circuits`
    keyword arg is used.
    """

    @accept_circuits_for_programs
    def inner_fn(
        name: str,
        programs: Union[CircuitRef, list[CircuitRef]],
    ) -> None:
        assert programs == [CIRCUIT_REF]

    with warnings.catch_warnings(record=True) as captured:
        inner_fn("hello", [CIRCUIT_REF])
        assert len(captured) == 0

    with warnings.catch_warnings(record=True) as captured:
        inner_fn("hello", circuits=[CIRCUIT_REF])  # type: ignore
        assert len(captured) == 1
        assert captured[0].category is DeprecationWarning

    with warnings.catch_warnings(record=True) as captured:
        inner_fn("hello", programs=[CIRCUIT_REF])
        assert len(captured) == 0


def test_compile_circuit_with_wrapper() -> None:
    """
    Test that `start_compile_job` is correctly invoked when the deprecated
    `circuits` keyword argument is supplied. The `accept_circuits_for_programs`
    decorator implements this.
    """
    with mock.patch("qnexus.client.jobs._compile.get_nexus_client") as gnc:
        mock_client = mock.MagicMock()

        mock_resp = mock.MagicMock()
        mock_resp.status_code = 202
        mock_resp.json.return_value = {
            "data": {
                "id": str(uuid4()),
                "attributes": {
                    "name": "blah",
                    "timestamps": {
                        "created": dt.datetime.now(),
                        "modified": dt.datetime.now(),
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

        gnc.post.return_value = mock_resp

        with warnings.catch_warnings(record=True) as captured:
            start_compile_job(
                name="foo",
                backend_config=QuantinuumConfig(device_name="whatever"),
                circuits=[CIRCUIT_REF],  # type: ignore
                project=PROJECT_REF,
            )
            assert captured[0].category is DeprecationWarning

        assert mock_client.post.call_count == 1
        assert (
            "program_id"
            in mock_client.post.call_args[1]["json"]["data"]["attributes"][
                "definition"
            ]["items"][0]
        )
