"""Client API for gpu decoder configs in Nexus."""

import base64
from datetime import datetime
from typing import Any, Union, cast
from uuid import UUID

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
from qnexus.models.references import DataframableList, GpuDecoderConfigRef, ProjectRef
from qnexus.models.scope import ScopeFilterEnum


class Params(
    ScopeFilter,
    SortFilter,
    PaginationFilter,
    NameFilter,
    CreatorFilter,
    ProjectRefFilter,
    PropertiesFilter,
    TimeFilter,
):
    """Params for filtering gpu decoder configs."""


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
) -> NexusIterator[GpuDecoderConfigRef]:
    """Get a NexusIterator over gpu decoder configs with optional filters.

    Examples:
        >>> import qnexus as qnx
        >>> all_configs = qnx.gpu_decoder_configs.get_all()
        >>> all_configs.df()

        >>> project_configs = qnx.gpu_decoder_configs.get_all(
        ...     name_like="my_config",
        ...     project=my_project_ref,
        ... )
    """

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
        resource_type="GpuDecoderConfig",
        nexus_url="/api/gpu_decoder_configs/v1beta",
        params=params,
        wrapper_method=_to_gpu_decoder_config_ref,
        nexus_client=get_nexus_client(),
    )


def _to_gpu_decoder_config_ref(
    page_json: dict[str, Any],
) -> DataframableList[GpuDecoderConfigRef]:
    """Convert JSON response dict to a list of GpuDecoderConfigRefs."""

    gpu_decoder_config_refs: DataframableList[GpuDecoderConfigRef] = DataframableList(
        []
    )

    for gpu_decoder_config_data in page_json["data"]:
        project_id = gpu_decoder_config_data["relationships"]["project"]["data"]["id"]
        project_details = next(
            proj for proj in page_json["included"] if proj["id"] == project_id
        )
        project = ProjectRef(
            id=project_id,
            annotations=Annotations.from_dict(project_details["attributes"]),
            contents_modified=project_details["attributes"]["contents_modified"],
            archived=project_details["attributes"]["archived"],
        )

        gpu_decoder_config_refs.append(
            GpuDecoderConfigRef(
                id=UUID(gpu_decoder_config_data["id"]),
                annotations=Annotations.from_dict(
                    gpu_decoder_config_data["attributes"]
                ),
                project=project,
            )
        )
    return gpu_decoder_config_refs


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
) -> GpuDecoderConfigRef:
    """
    Get a single gpu_decoder_config using filters. Throws an exception if the filters do
    not match exactly one object.

    Examples:
        >>> import qnexus as qnx
        >>> config_ref = qnx.gpu_decoder_configs.get(name="my_config")
    """
    if id:
        return _fetch_by_id(gpu_decoder_config_id=id, scope=scope)

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
    gpu_decoder_config: str,
    project: ProjectRef | None = None,
    name: str | None = None,
    description: str | None = None,
    properties: PropertiesDict | None = None,
) -> GpuDecoderConfigRef:
    """Upload a pytket GpuDecoderConfig to Nexus.

    Examples:
        >>> import qnexus as qnx
        >>> config_ref = qnx.gpu_decoder_configs.upload(
        ...     gpu_decoder_config=config_string,
        ...     name="my_config",
        ...     project=my_project_ref,
        ... )
    """
    project = project or get_active_project(project_required=True)
    project = cast(ProjectRef, project)

    attributes = {"contents": base64.b64encode(gpu_decoder_config.encode()).decode()}
    if name is None:
        raise ValueError("GpuDecoderConfig must have a name to be uploaded")

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
            "type": "gpu_decoder_config",
        }
    }

    res = get_nexus_client().post("/api/gpu_decoder_configs/v1beta", json=req_dict)

    # https://cqc.atlassian.net/browse/MUS-3054
    if res.status_code != 201:
        raise qnx_exc.ResourceCreateFailed(
            message=res.text, status_code=res.status_code
        )

    res_data_dict = res.json()["data"]

    return GpuDecoderConfigRef(
        id=UUID(res_data_dict["id"]),
        annotations=Annotations.from_dict(res_data_dict["attributes"]),
        project=project,
    )


@merge_properties_from_context
def update(
    ref: GpuDecoderConfigRef,
    name: str | None = None,
    description: str | None = None,
    properties: PropertiesDict | None = None,
) -> GpuDecoderConfigRef:
    """Update the annotations on a GpuDecoderConfigRef.

    Examples:
        >>> import qnexus as qnx
        >>> updated_ref = qnx.gpu_decoder_configs.update(
        ...     config_ref,
        ...     name="renamed_config",
        ... )
    """
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
            "type": "gpu_decoder_config",
        }
    }

    res = get_nexus_client().patch(
        f"/api/gpu_decoder_configs/v1beta/{ref.id}", json=req_dict
    )

    if res.status_code != 200:
        raise qnx_exc.ResourceUpdateFailed(
            message=res.text, status_code=res.status_code
        )

    res_dict = res.json()["data"]

    return GpuDecoderConfigRef(
        id=UUID(res_dict["id"]),
        annotations=Annotations.from_dict(res_dict["attributes"]),
        project=ref.project,
    )


@merge_scope_from_context
def _fetch_by_id(
    gpu_decoder_config_id: UUID | str, scope: ScopeFilterEnum = ScopeFilterEnum.USER
) -> GpuDecoderConfigRef:
    """Utility method for fetching directly by a unique identifier."""
    params = Params(
        scope=scope,
    ).model_dump(by_alias=True, exclude_unset=True, exclude_none=True)

    res = get_nexus_client().get(
        f"/api/gpu_decoder_configs/v1beta/{gpu_decoder_config_id}", params=params
    )

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

    return GpuDecoderConfigRef(
        id=UUID(res_dict["data"]["id"]),
        annotations=Annotations.from_dict(res_dict["data"]["attributes"]),
        project=project,
    )


@merge_scope_from_context
def _fetch_gpu_decoder_config(
    handle: GpuDecoderConfigRef, scope: ScopeFilterEnum = ScopeFilterEnum.USER
) -> str:
    """Utility method for fetching a gpu decoder config from a GpuDecoderConfigRef."""
    res = get_nexus_client().get(
        f"/api/gpu_decoder_configs/v1beta/{handle.id}",
        params={"scope": scope.value},
    )
    if res.status_code != 200:
        raise qnx_exc.ResourceFetchFailed(message=res.text, status_code=res.status_code)

    return base64.b64decode(res.json()["data"]["attributes"]["contents"]).decode()
