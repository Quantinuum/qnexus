"""Filter models for use by the client."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Literal, OrderedDict, Union

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from qnexus.models import CredentialIssuer, JobStatusEnum
from qnexus.models.annotations import PropertiesDict
from qnexus.models.references import JobType, ProjectRef
from qnexus.models.scope import ScopeFilterEnum
from qnexus.models.utils import AllowNone


def _format_property(key: str, value: bool | int | float | str) -> str:
    if isinstance(value, str):
        return f'({key},"{value}")'
    if isinstance(value, bool):
        return f"({key},{str(value).lower()})"
    return f"({key},{value})"


class PropertiesFilter(BaseModel):
    """Properties filters model.

    Example:
        >>> import qnexus as qnx
        >>> qnx.jobs.get_all(properties={"experiment": "vqe", "iteration": 5})
    """

    properties: PropertiesDict | None = Field(
        default=OrderedDict(),
        serialization_alias="filter[properties]",
        description="Filter by resource label value.",
    )

    @field_serializer("properties")
    def serialize_properties(self, properties: PropertiesDict) -> list[str]:
        """Serialize the id for a ProjectRef."""
        return [_format_property(key, value) for key, value in properties.items()]


class TimeFilter(BaseModel):
    """Resource time filters model.

    Example:
        >>> from datetime import datetime
        >>> import qnexus as qnx
        >>> qnx.projects.get_all(
        ...     created_after=datetime(2024, 1, 1),
        ...     modified_before=datetime(2024, 6, 30),
        ... )
    """

    created_before: Annotated[datetime | None, AllowNone] = Field(
        default=None,
        serialization_alias="filter[timestamps][created][before]",
        description="Show items created before this date.",
    )
    created_after: Annotated[datetime | None, AllowNone] = Field(
        default=None,
        serialization_alias="filter[timestamps][created][after]",
        description="Show items created after this date.",
    )
    modified_before: Annotated[datetime | None, AllowNone] = Field(
        default=None,
        serialization_alias="filter[timestamps][modified][before]",
        description="Show items modified before this date.",
    )
    modified_after: Annotated[datetime | None, AllowNone] = Field(
        default=None,
        serialization_alias="filter[timestamps][modified][after]",
        description="Show items modified after this date.",
    )


class PaginationFilter(BaseModel):
    """Pagination model.

    Example:
        >>> import qnexus as qnx
        >>> qnx.circuits.get_all(page_number=0, page_size=10)
    """

    page_number: int | None = Field(
        default=0,
        serialization_alias="page[number]",
        description="Specific page to return.",
    )
    page_size: int | None = Field(
        default=50,
        serialization_alias="page[size]",
        description="Size of page that is returned.",
    )


class CreatorFilter(BaseModel):
    """Creator email model."""

    creator_email: list[str] | None = Field(
        default=[],
        serialization_alias="filter[creator][email]",
        examples=["user@domain.com"],
        description="Filter by creator email.",
    )


class NameFilter(BaseModel):
    """Name model.

    Example:
        >>> import qnexus as qnx
        >>> qnx.projects.get_all(name_like="MyProject_")
        >>> qnx.projects.get(name="MyProject_123")
    """

    name_like: str | None = Field(
        default="",
        serialization_alias="filter[name_fuzzy]",
        description="Filter by name, fuzzy search.",
    )
    name_exact: list[str] | None = Field(
        default=None,
        serialization_alias="filter[name_exact]",
        description="Filter by name(s), exact match.",
    )


class SortFilterEnum(str, Enum):
    """SortFilterEnum model."""

    CREATED_ASC = "created"
    CREATED_DESC = "-created"
    MODIFIED_ASC = "modified"
    MODIFIED_DESC = "-modified"
    NAME_ASC = "name"
    NAME_DESC = "-name"


SortFilterString = Union[
    Literal["timestamps.created"],
    Literal["-timestamps.created"],
    Literal["timestamps.modified"],
    Literal["-timestamps.modified"],
    Literal["name"],
    Literal["-name"],
]

sortfilterenum_to_string: dict[SortFilterEnum, SortFilterString] = {
    SortFilterEnum.CREATED_ASC: "timestamps.created",
    SortFilterEnum.CREATED_DESC: "-timestamps.created",
    SortFilterEnum.MODIFIED_ASC: "timestamps.modified",
    SortFilterEnum.MODIFIED_DESC: "-timestamps.modified",
    SortFilterEnum.NAME_ASC: "name",
    SortFilterEnum.NAME_DESC: "-name",
}


class SortFilter(BaseModel):
    """Resource sorting model."""

    sort: (
        list[
            Union[
                Literal["timestamps.created"],
                Literal["-timestamps.created"],
                Literal["timestamps.modified"],
                Literal["-timestamps.modified"],
                Literal["name"],
                Literal["-name"],
            ]
        ]
        | None
    ) = Field(
        default=["-timestamps.created"],  # type: ignore
        serialization_alias="sort",
        description="Sort items.",
    )

    @staticmethod
    def convert_sort_filters(
        sort_filters: list[SortFilterEnum] | None,
    ) -> list[SortFilterString] | None:
        """Convert SortFilterEnum to SortFilterString."""
        return (
            [sortfilterenum_to_string[sort_filter] for sort_filter in sort_filters]
            if sort_filters
            else None
        )


class ProjectRefFilter(BaseModel):
    """Project Id filter"""

    project: Annotated[ProjectRef | None, AllowNone] = Field(
        default=None,
        serialization_alias="filter[project][id]",
        description="Filter by project ref",
    )

    @field_serializer("project")
    def serialize_project_ref(self, project: ProjectRef) -> str:
        """Serialize the id for a ProjectRef."""
        return str(project.id)


class ArchivedFilter(BaseModel):
    """Include or omit archived projects"""

    is_archived: Annotated[bool, AllowNone] = Field(
        default=False,
        serialization_alias="filter[archived]",
        description="Include or omit archived projects",
    )


JobStatusString = Union[
    Literal["COMPLETED"],
    Literal["QUEUED"],
    Literal["SUBMITTED"],
    Literal["RUNNING"],
    Literal["CANCELLED"],
    Literal["ERROR"],
    Literal["DEPLETED"],
    Literal["TERMINATED"],
]

jobstatusenum_to_string: dict[JobStatusEnum, JobStatusString] = {
    JobStatusEnum.COMPLETED: "COMPLETED",
    JobStatusEnum.QUEUED: "QUEUED",
    JobStatusEnum.SUBMITTED: "SUBMITTED",
    JobStatusEnum.RUNNING: "RUNNING",
    JobStatusEnum.CANCELLED: "CANCELLED",
    JobStatusEnum.ERROR: "ERROR",
    JobStatusEnum.DEPLETED: "DEPLETED",
    JobStatusEnum.TERMINATED: "TERMINATED",
}


class JobStatusFilter(BaseModel):
    """Job status filter.

    Example:
        >>> import qnexus as qnx
        >>> from qnexus.models.job_status import JobStatusEnum
        >>> qnx.jobs.get_all(job_status=[JobStatusEnum.RUNNING, JobStatusEnum.QUEUED])
    """

    status: list[JobStatusString] | None = Field(
        default=[  # type: ignore
            "COMPLETED",
            "QUEUED",
            "SUBMITTED",
            "RUNNING",
            "CANCELLED",
            "ERROR",
            "DEPLETED",
            "TERMINATED",
        ],
        serialization_alias="filter[status][status]",
        description="Filter by job status",
    )

    @staticmethod
    def convert_status_filters(
        status_filters: list[JobStatusEnum],
    ) -> list[JobStatusString]:
        """Convert SortFilterEnum to SortFilterString."""
        return [
            jobstatusenum_to_string[status_filter] for status_filter in status_filters
        ]


class JobTypeFilter(BaseModel):
    """Filter by job type.

    Example:
        >>> import qnexus as qnx
        >>> from qnexus.models.references import JobType
        >>> qnx.jobs.get_all(job_type=[JobType.EXECUTE])
    """

    job_type: list[JobType] | None = Field(
        default=[JobType.EXECUTE, JobType.COMPILE],
        serialization_alias="filter[job_type]",
        description="Filter by job_type",
    )

    model_config = ConfigDict(use_enum_values=True)


class DevicesFilter(BaseModel):
    """Filter by device details.

    Example:
        >>> import qnexus as qnx
        >>> from qnexus.models import IssuerEnum
        >>> qnx.devices.get_all(issuers=[IssuerEnum.QUANTINUUM])
    """

    backend: list[str] | None = None
    region: str | None = None
    ibm_instance: str | None = None
    ibm_region: str | None = None
    credential_ids: list[str] | None = None
    credential_names: list[str] | None = None
    is_local: bool | None = None


class CredentialsFilter(BaseModel):
    """Filter for credentials."""

    issuer: CredentialIssuer | str | None = None


class ScopeFilter(BaseModel):
    """Filter by scope.

    Example:
        >>> import qnexus as qnx
        >>> from qnexus.models.scope import ScopeFilterEnum
        >>> qnx.projects.get_all(scope=ScopeFilterEnum.ORG_ADMIN)
    """

    scope: ScopeFilterEnum = ScopeFilterEnum.USER

    model_config = ConfigDict(use_enum_values=True)
