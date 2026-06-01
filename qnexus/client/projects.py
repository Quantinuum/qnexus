"""Client API for projects in Nexus."""

import random
from datetime import datetime
from typing import Any, Literal, Union, cast
from uuid import UUID

import pandas as pd

import qnexus.exceptions as qnx_exc
from qnexus.client import get_nexus_client
from qnexus.client.nexus_iterator import NexusIterator
from qnexus.client.utils import handle_fetch_errors
from qnexus.context import get_active_project, merge_scope_from_context
from qnexus.models import Property
from qnexus.models.annotations import Annotations, CreateAnnotations, PropertiesDict
from qnexus.models.filters import (  # PropertiesFilter, # Not yet implemented
    ArchivedFilter,
    CreatorFilter,
    NameFilter,
    PaginationFilter,
    ScopeFilter,
    SortFilter,
    SortFilterEnum,
    TimeFilter,
)
from qnexus.models.job_status import WAITING_STATUS, JobStatusEnum
from qnexus.models.references import DataframableList, ProjectRef
from qnexus.models.scope import ScopeFilterEnum

# Colour-blind friendly colours from https://www.nature.com/articles/nmeth.1618
_COLOURS = ["#e69f00", "#56b4e9", "#009e73", "#f0e442", "#0072b2", "#d55e00", "#cc79a7"]


class Params(
    ScopeFilter,
    SortFilter,
    PaginationFilter,
    NameFilter,
    CreatorFilter,
    # PropertiesFilter, # Not yet implemented
    TimeFilter,
    ArchivedFilter,
):
    """Params for filtering projects"""


@merge_scope_from_context
def get_all(
    *,
    name_like: str | None = None,
    name_exact: list[str] | None = None,
    creator_email: list[str] | None = None,
    created_before: datetime | None = None,
    created_after: datetime | None = datetime(day=1, month=1, year=2023),
    modified_before: datetime | None = None,
    modified_after: datetime | None = None,
    is_archived: bool = False,
    sort_filters: list[SortFilterEnum] | None = None,
    page_number: int | None = None,
    page_size: int | None = None,
    scope: ScopeFilterEnum = ScopeFilterEnum.USER,
) -> NexusIterator[ProjectRef]:
    """Get a NexusIterator over projects with optional filters.

    Examples:
        >>> import qnexus as qnx
        >>> my_projects = qnx.projects.get_all(
        ...     name_like="experiment",
        ...     created_after=datetime(2026, 1, 1),
        ... )
        >>> my_projects.df()
    """

    params = Params(
        name_like=name_like,
        name_exact=name_exact,
        creator_email=creator_email,
        created_before=created_before,
        created_after=created_after,
        modified_before=modified_before,
        modified_after=modified_after,
        is_archived=is_archived,
        sort=SortFilter.convert_sort_filters(sort_filters),
        page_number=page_number,
        page_size=page_size,
        scope=scope,
    ).model_dump(
        by_alias=True,
        exclude_unset=True,
        exclude_none=True,
    )

    return NexusIterator(
        resource_type="Project",
        nexus_url="/api/projects/v1beta2",
        params=params,
        wrapper_method=_to_projectref,
        nexus_client=get_nexus_client(),
    )


def _to_projectref(data: dict[str, Any]) -> DataframableList[ProjectRef]:
    return DataframableList(
        [
            ProjectRef(
                id=project["id"],
                annotations=Annotations.from_dict(project["attributes"]),
                contents_modified=project["attributes"]["contents_modified"],
                archived=project["attributes"]["archived"],
            )
            for project in data["data"]
        ]
    )


@merge_scope_from_context
def get(
    *,
    id: Union[str, UUID, None] = None,
    name: str | None = None,
    name_like: str | None = None,
    creator_email: list[str] | None = None,
    created_before: datetime | None = None,
    created_after: datetime | None = datetime(day=1, month=1, year=2023),
    modified_before: datetime | None = None,
    modified_after: datetime | None = None,
    is_archived: bool = False,
    sort_filters: list[SortFilterEnum] | None = None,
    page_number: int | None = None,
    page_size: int | None = None,
    scope: ScopeFilterEnum = ScopeFilterEnum.USER,
) -> ProjectRef:
    """Get a single project using filters. Throws an exception if the filters do
    not match exactly one object.

    Examples:
        >>> import qnexus as qnx
        >>> project_ref = qnx.projects.get(name="MyProject")
        >>> project_ref = qnx.projects.get(id="dca33f7f-9619-4cf7-a3fb-56256b117d6e")
    """
    if id:
        return _fetch_by_id(id, scope=scope)

    return get_all(
        name_like=name_like,
        name_exact=[name] if name else None,
        creator_email=creator_email,
        created_before=created_before,
        created_after=created_after,
        modified_before=modified_before,
        modified_after=modified_after,
        is_archived=is_archived,
        sort_filters=sort_filters,
        page_number=page_number,
        page_size=page_size,
        scope=scope,
    ).try_unique_match()


def get_or_create(
    name: str,
    description: str | None = None,
    properties: PropertiesDict | None = None,
) -> ProjectRef:
    """Get a project reference if the projects exists (by name),
    otherwise create a new project using the supplied description and properties.

    Examples:
        >>> import qnexus as qnx
        >>> project_ref = qnx.projects.get_or_create(name="MyProject")
        >>> project_ref = qnx.projects.get_or_create(
        ...     name="MyProject",
        ...     description="A new experiment",
        ...     properties={"team": "quantum"},
        ... )
    """
    annotations = CreateAnnotations(
        name=name,
        description=description,
        properties=properties,
    )
    try:
        return get(name=annotations.name)
    except qnx_exc.ZeroMatches:
        return create(
            name=annotations.name,
            description=annotations.description,
            properties=annotations.properties,
        )


@merge_scope_from_context
def _fetch_by_id(
    project_id: UUID | str, scope: ScopeFilterEnum = ScopeFilterEnum.USER
) -> ProjectRef:
    """Utility method for fetching directly by a unique identifier."""
    params = Params(scope=scope).model_dump(
        by_alias=True, exclude_unset=True, exclude_none=True
    )

    res = get_nexus_client().get(f"/api/projects/v1beta2/{project_id}", params=params)

    handle_fetch_errors(res)

    res_dict = res.json()

    return ProjectRef(
        id=res_dict["data"]["id"],
        annotations=Annotations.from_dict(res_dict["data"]["attributes"]),
        contents_modified=res_dict["data"]["attributes"]["contents_modified"],
        archived=res_dict["data"]["attributes"]["archived"],
    )


def create(
    name: str,
    description: str | None = None,
    properties: PropertiesDict | None = None,
) -> ProjectRef:
    """Create a new project in Nexus.

    Examples:
        >>> import qnexus as qnx
        >>> project_ref = qnx.projects.create(
        ...     name="ProjectUnobtanium",
        ...     description="Chemistry experiments on unobtanium",
        ... )
    """
    attributes = {}
    annotations = CreateAnnotations(
        name=name,
        description=description,
        properties=properties,
    ).model_dump(exclude_none=True)
    attributes.update(annotations)

    req_dict = {
        "data": {
            "attributes": attributes,
            "relationships": {},
            "type": "project",
        }
    }

    res = get_nexus_client().post("/api/projects/v1beta2", json=req_dict)

    if res.status_code != 201:
        raise qnx_exc.ResourceCreateFailed(
            message=res.text, status_code=res.status_code
        )

    res_data_dict = res.json()["data"]

    return ProjectRef(
        id=UUID(res_data_dict["id"]),
        annotations=Annotations.from_dict(res_data_dict["attributes"]),
        contents_modified=res_data_dict["attributes"]["contents_modified"],
        archived=res_data_dict["attributes"]["archived"],
    )


def add_property(
    name: str,
    property_type: Literal["bool", "int", "float", "string"],
    project: ProjectRef | None = None,
    description: str | None = None,
    required: bool = False,
) -> None:
    """Add a property definition to a project.

    Examples:
        >>> import qnexus as qnx
        >>> qnx.projects.add_property(
        ...     name="iteration",
        ...     property_type="int",
        ...     project=project_ref,
        ... )
    """
    project = project or get_active_project(project_required=True)
    assert project, "ProjectRef required."

    # For now required to add properties in a seperate API step
    props_req_dict = {
        "data": {
            "attributes": {
                "name": name,
                "description": description,
                "property_type": property_type,
                "required": required,
                "color": random.choice(_COLOURS),
            },
            "relationships": {
                "project": {"data": {"id": str(project.id), "type": "project"}}
            },
            "type": "property",
        }
    }
    props_res = get_nexus_client().post(
        "/api/property_definitions/v1beta2", json=props_req_dict
    )

    if props_res.status_code != 201:
        raise qnx_exc.ResourceCreateFailed(
            message=props_res.text, status_code=props_res.status_code
        )


def get_properties(project: ProjectRef | None = None) -> DataframableList[Property]:
    """Get the property definitions for the Project.

    Examples:
        >>> import qnexus as qnx
        >>> qnx.projects.get_properties(project=project_ref).df()
    """
    # This will get all the properties (even if there are more than the page size),
    # but could be refactored if needed.

    project = project or get_active_project(project_required=True)
    assert project, "ProjectRef required."

    all_project_properties_iterator = NexusIterator(
        resource_type="Property",
        nexus_url="/api/property_definitions/v1beta2",
        params={"filter[project][id]": str(project.id)},
        wrapper_method=_to_property,
        nexus_client=get_nexus_client(),
    )

    return all_project_properties_iterator.list()


def _to_property(data: dict[str, Any]) -> DataframableList[Property]:
    return DataframableList(
        [
            Property(
                annotations=Annotations.from_dict(property_dict["attributes"]),
                property_type=property_dict["attributes"]["property_type"],
                required=property_dict["attributes"]["required"],
                color=property_dict["attributes"]["color"],
                id=property_dict["id"],
            )
            for property_dict in data["data"]
        ]
    )


def summarize(project: ProjectRef | None = None) -> pd.DataFrame:
    """Summarize the current state of a project.

    Examples:
        >>> import qnexus as qnx
        >>> qnx.projects.summarize(project=project_ref)
    """
    import qnexus.client.jobs as jobs_client

    project = project or get_active_project(project_required=True)
    project = cast(ProjectRef, project)

    all_jobs = jobs_client.get_all(project=project).list()

    return pd.DataFrame(
        {
            "project": project.annotations.name,
            "total_jobs": len(all_jobs),
            "pending_jobs": len(
                [job for job in all_jobs if job.last_status in WAITING_STATUS]
            ),
            "cancelled_jobs": len(
                [job for job in all_jobs if job.last_status == JobStatusEnum.CANCELLED]
            ),
            "errored_jobs": len(
                [job for job in all_jobs if job.last_status == JobStatusEnum.ERROR]
            ),
            "completed_jobs": len(
                [job for job in all_jobs if job.last_status == JobStatusEnum.COMPLETED]
            ),
        },
        index=[0],
    )


@merge_scope_from_context
def update(  # this does not update properties, properties should be added using add_property()
    project: ProjectRef,
    name: str | None = None,
    description: str | None = None,
    archive: bool = False,
    scope: ScopeFilterEnum = ScopeFilterEnum.USER,
) -> ProjectRef:
    """Update the details of a project.

    Examples:
        >>> import qnexus as qnx
        >>> updated = qnx.projects.update(project_ref, name="NewName")
        >>> qnx.projects.update(project_ref, archive=True)  # archive a project
    """
    req_dict = {
        "data": {
            "attributes": {
                "name": name,
                "description": description,
                "archived": archive,
            },
            "relationships": {},
            "type": "project",
        }
    }

    res = get_nexus_client().patch(
        f"/api/projects/v1beta2/{project.id}",
        json=req_dict,
        params={"scope": scope.value},
    )

    if res.status_code != 200:
        raise qnx_exc.ResourceUpdateFailed(
            message=res.text, status_code=res.status_code
        )

    res_data_dict = res.json()["data"]

    return ProjectRef(
        id=UUID(res_data_dict["id"]),
        annotations=Annotations.from_dict(res_data_dict["attributes"]),
        contents_modified=res_data_dict["attributes"]["contents_modified"],
        archived=res_data_dict["attributes"]["archived"],
    )


@merge_scope_from_context
def delete(project: ProjectRef, scope: ScopeFilterEnum = ScopeFilterEnum.USER) -> None:
    """Delete a project and all associated data in Nexus.
    Project must be archived first.
    WARNING: this will delete all data associated with the project.

    Examples:
        >>> import qnexus as qnx
        >>> qnx.projects.update(project_ref, archive=True)
        >>> qnx.projects.delete(project_ref)
    """
    res = get_nexus_client().delete(
        url=f"/api/projects/v1beta2/{project.id}",
        params={"scope": scope.value},
    )

    if res.status_code != 204:
        raise qnx_exc.ResourceDeleteFailed(
            message=res.text, status_code=res.status_code
        )
