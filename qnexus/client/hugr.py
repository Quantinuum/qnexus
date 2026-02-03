"""Client API for HUGR in Nexus."""

import base64
from datetime import datetime
from typing import Any, Literal, Union, cast
from uuid import UUID

from hugr.hugr import Hugr
from hugr.ops import Module
from hugr.package import Package, PackagePointer

import qnexus.exceptions as qnx_exc
from qnexus.client import get_nexus_client
from qnexus.client.nexus_iterator import NexusIterator
from qnexus.client.utils import handle_fetch_errors
from qnexus.context import (
    get_active_project,
    merge_project_from_context,
    merge_properties_from_context,
    merge_scope_from_context,
)
from qnexus.models import QuantinuumConfig
from qnexus.models.annotations import Annotations, CreateAnnotations, PropertiesDict
from qnexus.models.filters import (
    CreatorFilter,
    NameFilter,
    PaginationFilter,
    ProjectRefFilter,
    PropertiesFilter,
    ScopeFilter,
    SortFilter,
    SortFilterEnum,
    TimeFilter,
)
from qnexus.models.references import (
    DataframableList,
    ExecutionProgram,
    HUGRRef,
    ProjectRef,
)
from qnexus.models.scope import ScopeFilterEnum


class Params(
    SortFilter,
    PaginationFilter,
    NameFilter,
    CreatorFilter,
    ProjectRefFilter,
    PropertiesFilter,
    TimeFilter,
    ScopeFilter,
):
    """Params for filtering HUGRs."""


@merge_scope_from_context
@merge_project_from_context
def get_all(
    *,
    name_like: str | None = None,
    name_exact: list[str] | None = None,
    creator_email: list[str] | None = None,
    project: ProjectRef | None = None,
    properties: PropertiesDict | None = None,
    created_before: datetime | None = None,
    created_after: datetime | None = datetime(day=1, month=1, year=2023),
    modified_before: datetime | None = None,
    modified_after: datetime | None = None,
    sort_filters: list[SortFilterEnum] | None = None,
    page_number: int | None = None,
    page_size: int | None = None,
    scope: ScopeFilterEnum = ScopeFilterEnum.USER,
) -> NexusIterator[HUGRRef]:
    """Get a NexusIterator over HUGRs with optional filters."""

    params = Params(
        name_like=name_like,
        name_exact=name_exact,
        creator_email=creator_email,
        properties=properties,
        project=project,
        created_before=created_before,
        created_after=created_after,
        modified_before=modified_before,
        modified_after=modified_after,
        sort=SortFilter.convert_sort_filters(sort_filters),
        page_number=page_number,
        page_size=page_size,
        scope=scope,
    ).model_dump(by_alias=True, exclude_unset=True, exclude_none=True)

    return NexusIterator(
        resource_type="HUGR",
        nexus_url="/api/hugr/v1beta",
        params=params,
        wrapper_method=_to_hugr_ref,
        nexus_client=get_nexus_client(),
    )


def _to_hugr_ref(page_json: dict[str, Any]) -> DataframableList[HUGRRef]:
    """Convert JSON response dict to a list of HUGRRefs."""

    hugr_refs: DataframableList[HUGRRef] = DataframableList([])

    for hugr_data in page_json["data"]:
        project_id = hugr_data["relationships"]["project"]["data"]["id"]
        project_details = next(
            proj for proj in page_json["included"] if proj["id"] == project_id
        )
        project = ProjectRef(
            id=project_id,
            annotations=Annotations.from_dict(project_details["attributes"]),
            contents_modified=project_details["attributes"]["contents_modified"],
            archived=project_details["attributes"]["archived"],
        )

        hugr_refs.append(
            HUGRRef(
                id=UUID(hugr_data["id"]),
                annotations=Annotations.from_dict(hugr_data["attributes"]),
                project=project,
            )
        )
    return hugr_refs


@merge_scope_from_context
def get(
    *,
    id: Union[UUID, str, None] = None,
    name: str | None = None,
    name_like: str | None = None,
    creator_email: list[str] | None = None,
    project: ProjectRef | None = None,
    properties: PropertiesDict | None = None,
    created_before: datetime | None = None,
    created_after: datetime | None = datetime(day=1, month=1, year=2023),
    modified_before: datetime | None = None,
    modified_after: datetime | None = None,
    sort_filters: list[SortFilterEnum] | None = None,
    page_number: int | None = None,
    page_size: int | None = None,
    scope: ScopeFilterEnum = ScopeFilterEnum.USER,
) -> HUGRRef:
    """
    Get a single HUGR using filters. Throws an exception if the filters do
    not match exactly one object.
    """

    if id:
        return _fetch_by_id(hugr_id=id, scope=scope)

    return get_all(
        name_like=name_like,
        name_exact=[name] if name else None,
        creator_email=creator_email,
        properties=properties,
        project=project,
        created_before=created_before,
        created_after=created_after,
        modified_before=modified_before,
        modified_after=modified_after,
        sort_filters=sort_filters,
        page_number=page_number,
        page_size=page_size,
        scope=scope,
    ).try_unique_match()


@merge_properties_from_context
def upload(
    hugr_package: Package | PackagePointer | Hugr[Module],
    name: str,
    project: ProjectRef | None = None,
    description: str | None = None,
    properties: PropertiesDict | None = None,
) -> HUGRRef:
    """Upload a HUGR to Nexus."""
    project = project or get_active_project(project_required=True)
    project = cast(ProjectRef, project)

    match hugr_package:
        case PackagePointer():
            package = hugr_package.package
        case Hugr():
            package = Package([hugr_package])
        case Package():
            package = hugr_package
        case _:
            raise ValueError(f"Unsupported type for HUGR upload: {type(hugr_package)}.")
    attributes = {"contents": _encode_hugr(package)}

    annotations = CreateAnnotations(
        name=name,
        description=description,
        properties=properties,
    ).model_dump(exclude_none=True)
    attributes.update(annotations)
    relationships = {"project": {"data": {"id": str(project.id), "type": "project"}}}

    req_dict = {
        "data": {
            "attributes": attributes,
            "relationships": relationships,
            "type": "hugr",
        }
    }

    res = get_nexus_client().post("/api/hugr/v1beta", json=req_dict)

    if res.status_code != 201:
        raise qnx_exc.ResourceCreateFailed(
            message=res.text, status_code=res.status_code
        )

    res_data_dict = res.json()["data"]

    return HUGRRef(
        id=UUID(res_data_dict["id"]),
        annotations=Annotations.from_dict(res_data_dict["attributes"]),
        project=project,
    )


@merge_properties_from_context
def update(
    ref: HUGRRef,
    name: str | None = None,
    description: str | None = None,
    properties: PropertiesDict | None = None,
) -> HUGRRef:
    """Update the annotations on a HUGRRef."""
    ref_annotations = ref.annotations.model_dump()
    annotations = Annotations(
        name=name,
        description=description,
        properties=properties if properties else PropertiesDict(),
    ).model_dump(exclude_none=True)
    ref_annotations.update(annotations)

    req_dict = {
        "data": {
            "attributes": annotations,
            "relationships": {},
            "type": "hugr",
        }
    }

    res = get_nexus_client().patch(f"/api/hugr/v1beta/{ref.id}", json=req_dict)

    if res.status_code != 200:
        raise qnx_exc.ResourceUpdateFailed(
            message=res.text, status_code=res.status_code
        )

    res_dict = res.json()["data"]

    return HUGRRef(
        id=UUID(res_dict["id"]),
        annotations=Annotations.from_dict(res_dict["attributes"]),
        project=ref.project,
    )


def cost(
    programs: HUGRRef | list[HUGRRef],
    n_shots: int | list[int],
    project: ProjectRef | None = None,
    system_name: Literal["Helios-1"] = "Helios-1",
) -> float:
    """Estimate the cost (in HQC) of running Hugr programs for n_shots
    number of shots on a Quantinuum Helios system.

    NB: This will execute a costing job on a dedicated cost estimation device.
        Once run, the cost will be visible also in the Nexus web portal
        as part of the job.
    """
    import qnexus as qnx

    if isinstance(programs, HUGRRef):
        programs = [programs]

    job_ref = qnx.start_execute_job(
        programs=cast(list[ExecutionProgram], programs),
        n_shots=n_shots,
        backend_config=QuantinuumConfig(device_name=f"{system_name}SC"),
        project=project,
        name="Hugr cost estimation job",
    )
    status = qnx.jobs.wait_for(job_ref)

    return cast(float, status.cost)


@merge_scope_from_context
def _fetch_by_id(
    hugr_id: UUID | str, scope: ScopeFilterEnum = ScopeFilterEnum.USER
) -> HUGRRef:
    """Utility method for fetching directly by a unique identifier."""

    params = Params(
        scope=scope,
    ).model_dump(by_alias=True, exclude_unset=True, exclude_none=True)

    res = get_nexus_client().get(f"/api/hugr/v1beta/{hugr_id}", params=params)

    handle_fetch_errors(res)

    res_dict = res.json()

    project_id = res_dict["data"]["relationships"]["project"]["data"]["id"]
    project_details = next(
        proj for proj in res_dict["included"] if proj["id"] == project_id
    )
    project = ProjectRef(
        id=project_id,
        annotations=Annotations.from_dict(project_details["attributes"]),
        contents_modified=project_details["attributes"]["contents_modified"],
        archived=project_details["attributes"]["archived"],
    )

    return HUGRRef(
        id=UUID(res_dict["data"]["id"]),
        annotations=Annotations.from_dict(res_dict["data"]["attributes"]),
        project=project,
    )


@merge_scope_from_context
def _fetch_hugr_package(
    handle: HUGRRef, scope: ScopeFilterEnum = ScopeFilterEnum.USER
) -> Package:
    """Utility method for fetching a HUGR Package from a HUGRRef."""

    hugr_bytes = _fetch_hugr_bytes(handle=handle, scope=scope)
    return Package.from_bytes(envelope=hugr_bytes)


@merge_scope_from_context
def _fetch_hugr_bytes(
    handle: HUGRRef, scope: ScopeFilterEnum = ScopeFilterEnum.USER
) -> bytes:
    """Utility method for fetching HUGR bytes from a HUGRRef."""
    res = get_nexus_client().get(
        f"/api/hugr/v1beta/{handle.id}",
        params={"scope": scope.value},
    )
    if res.status_code != 200:
        raise qnx_exc.ResourceFetchFailed(message=res.text, status_code=res.status_code)

    contents = res.json()["data"]["attributes"]["contents"]
    return base64.b64decode(contents)


def _encode_hugr(hugr_package: Package) -> str:
    """Utility method for encoding a HUGR Package as base64-encoded string"""
    return base64.b64encode(hugr_package.to_bytes()).decode("utf-8")
