"""Client API for wasm_modules in Nexus."""

import base64
from datetime import datetime
from typing import Any, Union, cast
from uuid import UUID

from pytket.wasm.wasm import WasmModuleHandler

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
from qnexus.models.references import DataframableList, ProjectRef, WasmModuleRef
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
    """Params for filtering wasm_modules."""


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
) -> NexusIterator[WasmModuleRef]:
    """Get a NexusIterator over wasm_modules with optional filters.

    Examples:
        >>> import qnexus as qnx
        >>> all_wasm = qnx.wasm_modules.get_all()
        >>> all_wasm.df()

        >>> project_wasm = qnx.wasm_modules.get_all(
        ...     name_like="my_module",
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
        resource_type="WasmModule",
        nexus_url="/api/wasm/v1beta",
        params=params,
        wrapper_method=_to_wasm_module_ref,
        nexus_client=get_nexus_client(),
    )


def _to_wasm_module_ref(page_json: dict[str, Any]) -> DataframableList[WasmModuleRef]:
    """Convert JSON response dict to a list of WasmModuleRefs."""

    wasm_module_refs: DataframableList[WasmModuleRef] = DataframableList([])

    for wasm_module_data in page_json["data"]:
        project_id = wasm_module_data["relationships"]["project"]["data"]["id"]
        project_details = next(
            proj for proj in page_json["included"] if proj["id"] == project_id
        )
        project = ProjectRef(
            id=project_id,
            annotations=Annotations.from_dict(project_details["attributes"]),
            contents_modified=project_details["attributes"]["contents_modified"],
            archived=project_details["attributes"]["archived"],
        )

        wasm_module_refs.append(
            WasmModuleRef(
                id=UUID(wasm_module_data["id"]),
                annotations=Annotations.from_dict(wasm_module_data["attributes"]),
                project=project,
            )
        )
    return wasm_module_refs


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
) -> WasmModuleRef:
    """
    Get a single wasm_module using filters. Throws an exception if the filters do
    not match exactly one object.

    Examples:
        >>> import qnexus as qnx
        >>> wasm_ref = qnx.wasm_modules.get(name="my_wasm_module")
    """
    if id:
        return _fetch_by_id(wasm_module_id=id, scope=scope)

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
    wasm_module_handler: WasmModuleHandler,
    project: ProjectRef | None = None,
    name: str | None = None,
    description: str | None = None,
    properties: PropertiesDict | None = None,
) -> WasmModuleRef:
    """Upload a pytket WasmModule to Nexus.

    Examples:
        >>> import qnexus as qnx
        >>> from pytket.wasm import WasmModuleHandler
        >>> wasm_handler = WasmModuleHandler("my_wasm_module.wasm")
        >>> wasm_ref = qnx.wasm_modules.upload(
        ...     wasm_handler,
        ...     name="my_wasm_module",
        ...     project=my_project_ref,
        ... )
    """
    project = project or get_active_project(project_required=True)
    project = cast(ProjectRef, project)

    attributes = {"contents": str(wasm_module_handler.bytecode_base64, "utf-8")}
    if name is None:
        raise ValueError("WasmModule must have a name to be uploaded")

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
            "type": "wasm",
        }
    }

    res = get_nexus_client().post("/api/wasm/v1beta", json=req_dict)

    # https://cqc.atlassian.net/browse/MUS-3054
    if res.status_code != 201:
        raise qnx_exc.ResourceCreateFailed(
            message=res.text, status_code=res.status_code
        )

    res_data_dict = res.json()["data"]

    return WasmModuleRef(
        id=UUID(res_data_dict["id"]),
        annotations=Annotations.from_dict(res_data_dict["attributes"]),
        project=project,
    )


@merge_properties_from_context
def update(
    ref: WasmModuleRef,
    name: str | None = None,
    description: str | None = None,
    properties: PropertiesDict | None = None,
) -> WasmModuleRef:
    """Update the annotations on a WasmModuleRef.

    Examples:
        >>> import qnexus as qnx
        >>> updated_ref = qnx.wasm_modules.update(
        ...     wasm_ref,
        ...     name="renamed_module",
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
            "type": "wasm_module",
        }
    }

    res = get_nexus_client().patch(f"/api/wasm/v1beta/{ref.id}", json=req_dict)

    if res.status_code != 200:
        raise qnx_exc.ResourceUpdateFailed(
            message=res.text, status_code=res.status_code
        )

    res_dict = res.json()["data"]

    return WasmModuleRef(
        id=UUID(res_dict["id"]),
        annotations=Annotations.from_dict(res_dict["attributes"]),
        project=ref.project,
    )


@merge_scope_from_context
def _fetch_by_id(
    wasm_module_id: UUID | str, scope: ScopeFilterEnum = ScopeFilterEnum.USER
) -> WasmModuleRef:
    """Utility method for fetching directly by a unique identifier."""
    params = Params(
        scope=scope,
    ).model_dump(by_alias=True, exclude_unset=True, exclude_none=True)

    res = get_nexus_client().get(f"/api/wasm/v1beta/{wasm_module_id}", params=params)

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

    return WasmModuleRef(
        id=UUID(res_dict["data"]["id"]),
        annotations=Annotations.from_dict(res_dict["data"]["attributes"]),
        project=project,
    )


@merge_scope_from_context
def _fetch_wasm_module(
    handle: WasmModuleRef, scope: ScopeFilterEnum = ScopeFilterEnum.USER
) -> WasmModuleHandler:
    """Utility method for fetching a pytket WasmModuleHandler from a WasmModuleRef."""
    res = get_nexus_client().get(
        f"/api/wasm/v1beta/{handle.id}",
        params={"scope": scope.value},
    )
    if res.status_code != 200:
        raise qnx_exc.ResourceFetchFailed(message=res.text, status_code=res.status_code)

    res_data_attributes_dict = res.json()["data"]["attributes"]

    return WasmModuleHandler(
        wasm_module=base64.b64decode(res_data_attributes_dict["contents"]), check=False
    )
