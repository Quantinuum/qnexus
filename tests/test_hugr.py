"""Basic checks for HUGR functionality."""

import base64
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import pytest
from hugr.package import Package

import qnexus as qnx
from qnexus.exceptions import IncompatibleResultVersion
from qnexus.models.annotations import Annotations
from qnexus.models.references import ExecutionResultRef, ProjectRef, ResultVersions


def test_raises_when_trying_to_get_raw_results_from_pytket_result() -> None:
    """Given an ExecutionResultRef to a pytket result, it will raise an error
    if the user tries to get anything other than the default results."""

    ref = ExecutionResultRef(
        id=uuid.uuid4(),
        annotations=Annotations(),
        project=ProjectRef(
            id=uuid.uuid4(),
            annotations=Annotations(),
            contents_modified=datetime.now(timezone.utc),
        ),
    )

    with pytest.raises(IncompatibleResultVersion):
        ref.download_result(version=ResultVersions.RAW)


def test_uploading_hugr_module_keeps_used_extensions() -> None:
    """Creating a package for a bare HUGR must retain its extension definitions."""
    original_package = Package.from_bytes(
        Path("tests/data/example_bell.hugr").read_bytes()
    )
    hugr = original_package.modules[0]
    used_extension_names = {
        extension.name
        for extension in original_package.extensions
        if extension.name
        in {
            extension.name
            for extension in hugr.used_extensions().used_extensions.all_extensions
        }
    }
    project = ProjectRef(
        id=uuid.uuid4(),
        annotations=Annotations(),
        contents_modified=datetime.now(timezone.utc),
    )

    with mock.patch("qnexus.client.hugr.get_nexus_client") as get_client:
        response = mock.MagicMock()
        response.status_code = 201
        response.json.return_value = {
            "data": {
                "id": str(uuid.uuid4()),
                "attributes": {
                    "name": "example bell",
                    "timestamps": {
                        "created": datetime.now(timezone.utc).isoformat(),
                        "modified": datetime.now(timezone.utc).isoformat(),
                    },
                },
            }
        }
        get_client.return_value.post.return_value = response

        qnx.hugr.upload(hugr, name="example bell", project=project)

    contents = get_client.return_value.post.call_args.kwargs["json"]["data"][
        "attributes"
    ]["contents"]
    uploaded_package = Package.from_bytes(base64.b64decode(contents))
    uploaded_extension_names = {
        extension.name for extension in uploaded_package.extensions
    }

    assert uploaded_extension_names == used_extension_names


def test_uploading_hugr_module_as_bytes() -> None:
    """A HUGR should be uploadable in byte form without deserialising first."""
    pkg_bytes = Path("tests/data/example_bell.hugr").read_bytes()
    project = ProjectRef(
        id=uuid.uuid4(),
        annotations=Annotations(),
        contents_modified=datetime.now(timezone.utc),
    )

    with mock.patch("qnexus.client.hugr.get_nexus_client") as get_client:
        response = mock.MagicMock()
        response.status_code = 201
        response.json.return_value = {
            "data": {
                "id": str(uuid.uuid4()),
                "attributes": {
                    "name": "example bell",
                    "timestamps": {
                        "created": datetime.now(timezone.utc).isoformat(),
                        "modified": datetime.now(timezone.utc).isoformat(),
                    },
                },
            }
        }
        get_client.return_value.post.return_value = response

        qnx.hugr.upload(pkg_bytes, name="example bell", project=project)

    contents = get_client.return_value.post.call_args.kwargs["json"]["data"][
        "attributes"
    ]["contents"]
    uploaded_bytes = base64.b64decode(contents)

    assert pkg_bytes == uploaded_bytes
