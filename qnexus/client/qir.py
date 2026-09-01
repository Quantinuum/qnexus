"""Client API for QIR in Nexus."""

import base64
import warnings
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
    merge_target_region_from_context,
)
from qnexus.models import HeliosConfig, QuantinuumConfig
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
    GpuDecoderConfigRef,
    ProjectRef,
    QIRRef,
    WasmModuleRef,
)
from qnexus.models.region import Region, _get_costing_system_for_region
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
    """Params for filtering QIRs."""


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
) -> NexusIterator[QIRRef]:
    """Get a NexusIterator over QIRs with optional filters.

    Examples:
        >>> import qnexus as qnx
        >>> all_qirs = qnx.qir.get_all(project=project_ref)
        >>> all_qirs.df()
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
        resource_type="QIR",
        nexus_url="/api/qir/v1beta",
        params=params,
        wrapper_method=_to_qir_ref,
        nexus_client=get_nexus_client(),
    )


def _to_qir_ref(page_json: dict[str, Any]) -> DataframableList[QIRRef]:
    """Convert JSON response dict to a list of QIRRefs."""

    qir_refs: DataframableList[QIRRef] = DataframableList([])

    for qir_data in page_json["data"]:
        project_id = qir_data["relationships"]["project"]["data"]["id"]
        project_details = next(
            proj for proj in page_json["included"] if proj["id"] == project_id
        )
        project = ProjectRef(
            id=project_id,
            annotations=Annotations.from_dict(project_details["attributes"]),
            contents_modified=project_details["attributes"]["contents_modified"],
            archived=project_details["attributes"]["archived"],
        )

        qir_refs.append(
            QIRRef(
                id=UUID(qir_data["id"]),
                annotations=Annotations.from_dict(qir_data["attributes"]),
                project=project,
            )
        )
    return qir_refs


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
) -> QIRRef:
    """
    Get a single QIR using filters. Throws an exception if the filters do
    not match exactly one object.

    Examples:
        >>> import qnexus as qnx
        >>> qir_ref = qnx.qir.get(name="my_qir", project=project_ref)
    """

    if id:
        return _fetch_by_id(qir_id=id, scope=scope)

    return get_all(
        name_exact=[name] if name else None,
        name_like=name_like,
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
    qir: bytes,
    name: str,
    project: ProjectRef | None = None,
    description: str | None = None,
    properties: PropertiesDict | None = None,
) -> QIRRef:
    """Upload a QIR to Nexus.

    Examples:
        >>> import qnexus as qnx
        >>> qir_ref = qnx.qir.upload(
        ...     qir=qir_bytes,
        ...     name="my_qir_program",
        ...     project=project_ref,
        ... )
    """
    project = project or get_active_project(project_required=True)
    project = cast(ProjectRef, project)

    attributes = {"contents": _encode_qir(qir)}

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
            "type": "qir",
        }
    }

    res = get_nexus_client().post("/api/qir/v1beta", json=req_dict)

    if res.status_code != 201:
        raise qnx_exc.ResourceCreateFailed(
            message=res.text, status_code=res.status_code
        )

    res_data_dict = res.json()["data"]

    return QIRRef(
        id=UUID(res_data_dict["id"]),
        annotations=Annotations.from_dict(res_data_dict["attributes"]),
        project=project,
    )


@merge_properties_from_context
def update(
    ref: QIRRef,
    name: str | None = None,
    description: str | None = None,
    properties: PropertiesDict | None = None,
) -> QIRRef:
    """Update the annotations on a QIRRef.

    Examples:
        >>> import qnexus as qnx
        >>> updated = qnx.qir.update(qir_ref, name="renamed_qir")
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
            "type": "qir",
        }
    }

    res = get_nexus_client().patch(f"/api/qir/v1beta/{ref.id}", json=req_dict)

    if res.status_code != 200:
        raise qnx_exc.ResourceUpdateFailed(
            message=res.text, status_code=res.status_code
        )

    res_dict = res.json()["data"]

    return QIRRef(
        id=UUID(res_dict["id"]),
        annotations=Annotations.from_dict(res_dict["attributes"]),
        project=ref.project,
    )


def cost(
    programs: QIRRef | list[QIRRef],
    n_shots: int | list[int],
    project: ProjectRef | None = None,
    system_name: str | None = None,
    timeout: float | None = None,
    target_region: Region | None = None,
) -> float:
    """Estimate the cost (in HQC) of running QIR programs for n_shots
    number of shots on a Quantinuum Helios system.

    NB: This will execute a costing job on a dedicated cost estimation device.
        Once run, the cost will be visible also in the Nexus web portal
        as part of the job.
    """
    import qnexus as qnx

    warnings.warn(
        "qir.cost() is deprecated for Helios systems or newer. Please update to use qir.cost_confidence() instead.",
        category=DeprecationWarning,
    )

    system_name = system_name or _get_costing_system_for_region(target_region)

    if isinstance(programs, QIRRef):
        programs = [programs]

    job_ref = qnx.start_execute_job(
        programs=cast(list[ExecutionProgram], programs),
        n_shots=n_shots,
        backend_config=_costing_backend_config(system_name),
        project=project,
        name="QIR cost estimation job",
    )
    status = qnx.jobs.wait_for(job_ref, timeout=timeout)

    return cast(float, status.cost)


@merge_target_region_from_context
def cost_confidence(
    programs: QIRRef | list[QIRRef],
    n_shots: int | list[int],
    project: ProjectRef | None = None,
    system_name: str | None = None,
    timeout: float | None = None,
    target_region: Region | None = None,
    wasm_module: WasmModuleRef | None = None,
    gpu_decoder_config: GpuDecoderConfigRef | None = None,
) -> list[tuple[float, float]]:
    """Estimate the cost (in HQC) of running QIR programs for n_shots
    number of shots on a Quantinuum Helios system.

    Returns a list of tuples of (cost, confidence) for each job item.

    NB: This will execute a costing job on a dedicated cost estimation device.
        Once run, the cost will be visible also in the Nexus web portal
        as part of the job.

    Args:
        timeout: Overall timeout in seconds to wait for the costing job to
            complete. None for no timeout (default: None).
    """
    import qnexus as qnx

    system_name = system_name or _get_costing_system_for_region(target_region)

    if isinstance(programs, QIRRef):
        programs = [programs]

    job_ref = qnx.start_execute_job(
        programs=cast(list[ExecutionProgram], programs),
        n_shots=n_shots,
        backend_config=_costing_backend_config(system_name),
        project=project,
        name="QIR cost estimation job",
        target_region=target_region,
        wasm_module=wasm_module,
        gpu_decoder_config=gpu_decoder_config,
    )

    qnx.jobs.wait_for(job_ref, timeout=timeout)

    return qnx.jobs.cost_confidence(job_ref)


def _costing_backend_config(system_name: str) -> HeliosConfig | QuantinuumConfig:
    """Build the syntax-checker backend config for QIR cost estimation."""
    syntax_checker_name = f"{system_name}SC"
    if "Helios" in system_name:
        return HeliosConfig(system_name=syntax_checker_name)
    return QuantinuumConfig(device_name=syntax_checker_name)


@merge_scope_from_context
def _fetch_by_id(
    qir_id: UUID | str, scope: ScopeFilterEnum = ScopeFilterEnum.USER
) -> QIRRef:
    """Utility method for fetching directly by a unique identifier."""

    params = Params(
        scope=scope,
    ).model_dump(by_alias=True, exclude_unset=True, exclude_none=True)

    res = get_nexus_client().get(f"/api/qir/v1beta/{qir_id}", params=params)

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

    return QIRRef(
        id=UUID(res_dict["data"]["id"]),
        annotations=Annotations.from_dict(res_dict["data"]["attributes"]),
        project=project,
    )


@merge_scope_from_context
def _fetch_qir(handle: QIRRef, scope: ScopeFilterEnum = ScopeFilterEnum.USER) -> bytes:
    """Utility method for fetching QIR bytes from a QIRRef."""
    res = get_nexus_client().get(
        f"/api/qir/v1beta/{handle.id}",
        params={"scope": scope.value},
    )
    handle_fetch_errors(res)

    contents: str = res.json()["data"]["attributes"]["contents"]
    return _decode_qir(contents)


def _encode_qir(qir: bytes) -> str:
    """Utility method for encoding QIR bytes as base64-encoded string"""
    return base64.b64encode(qir).decode("utf-8")


def _decode_qir(contents: str) -> bytes:
    """Utility method for decoding a base64-encoded string into QIR bytes"""
    return base64.b64decode(contents)
