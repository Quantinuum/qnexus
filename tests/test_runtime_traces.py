"""Tests for getting and downloading runtime traces."""

import json
import uuid
from typing import cast
from unittest import mock

from selene_core.trace import Trace

import qnexus as qnx
from qnexus.models.references import ExecuteJobRef


def test_runtime_traces_get_and_download() -> None:
    """Test that we can get runtime traces for a job."""

    job_id = str(uuid.uuid4())
    job_item_uuid = str(uuid.uuid4())
    project_id = str(uuid.uuid4())
    mock_job_json = {
        "data": {
            "id": job_id,
            "attributes": {
                "timestamps": {
                    "created": "2026-07-27T12:05:14.506206Z",
                    "modified": "2026-07-27T12:05:26.749969Z",
                },
                "name": "example job",
                "properties": {},
                "job_type": "execute",
                "status": {
                    "status": "COMPLETED",
                    "message": "The job is completed.",
                    "completed_time": "2026-07-27T12:05:26.749969+00:00",
                    "queued_time": "2026-07-27T12:05:20.792869+00:00",
                    "submitted_time": "2026-07-27T12:05:16.926538+00:00",
                    "running_time": "2026-07-27T12:05:25.290861+00:00",
                    "cost": 5,
                },
                "definition": {
                    "job_definition_type": "execute_job_definition",
                    "backend_config": {
                        "type": "HeliosConfig",
                        "device_name": "Helios-1E",
                    },
                    "batch_id": "",
                    "valid_check": True,
                    "language": "AUTO",
                    "wasm_module_id": None,
                    "target_region": "us",
                    "is_local": True,
                    "total_items": 1,
                    "items": [
                        {
                            "program_id": str(uuid.uuid4()),
                            "n_shots": 10,
                            "max_cost": 10000,
                            "n_qubits": 5,
                            "item_id": 1,
                            "item_uuid": job_item_uuid,
                            "result_id": str(uuid.uuid4()),
                            "external_handle": job_item_uuid,
                            "status": {
                                "status": "COMPLETED",
                                "message": "Program has completed",
                                "completed_time": "2026-07-27T12:05:25.095807+00:00",
                                "queued_time": "2026-07-27T12:05:20.753000+00:00",
                                "submitted_time": "2026-07-27T12:05:15.654363+00:00",
                                "cost": 5,
                                "n_shots_completed": 10,
                            },
                            "result_type": "QSYS",
                            "has_runtime_traces": True,
                        }
                    ],
                },
            },
            "relationships": {
                "project": {
                    "links": {"self": "fakelink"},
                    "data": {"id": project_id, "type": "project"},
                },
            },
            "links": {"self": "fakelink"},
            "type": "job",
        },
        "included": [
            {
                "id": project_id,
                "attributes": {
                    "timestamps": {
                        "created": "2025-06-23T09:24:35.159226Z",
                        "modified": "2025-06-23T09:24:35.159226Z",
                    },
                    "name": "Nexus Canary",
                    "properties": {},
                    "archived": False,
                    "contents_modified": "2026-07-28T08:08:17.713168Z",
                },
                "relationships": {
                    "creator": {
                        "links": {"self": "fakelink"},
                        "data": {
                            "id": "4397f830-af57-47df-9f85-1a50f7260b31",
                            "type": "user",
                        },
                    }
                },
                "links": {"self": "fakelink"},
                "type": "project",
            }
        ],
    }

    with open("tests/data/runtime_traces_example.json", "r") as f:
        runtime_traces_example = json.load(f)

    with (
        mock.patch("qnexus.client.jobs.get_nexus_client") as fetch_job_client_mock,
        mock.patch(
            "qnexus.client.jobs._execute.get_nexus_client"
        ) as runtime_traces_client_mock,
    ):
        fetch_job_client = mock.MagicMock()
        mock_get_job_resp = mock.MagicMock()
        mock_get_job_resp.status_code = 200
        mock_get_job_resp.json.return_value = mock_job_json
        fetch_job_client.get.return_value = mock_get_job_resp

        fetch_job_client_mock.return_value = fetch_job_client
        runtime_traces_client_mock.return_value = fetch_job_client

        job_ref = qnx.jobs.get(id=job_id)
        job_ref = cast(ExecuteJobRef, job_ref)
        runtime_traces = qnx.jobs.runtime_traces(job_ref)
        assert len(runtime_traces) == 1

        download_runtime_traces_client = mock.MagicMock()
        mock_download_runtime_traces_resp = mock.MagicMock()
        mock_download_runtime_traces_resp.status_code = 200
        mock_download_runtime_traces_resp.json.return_value = runtime_traces_example
        download_runtime_traces_client.get.return_value = (
            mock_download_runtime_traces_resp
        )
        runtime_traces_client_mock.return_value = download_runtime_traces_client

        downloaded = runtime_traces[0].download_runtime_traces()
        assert isinstance(downloaded, Trace)
