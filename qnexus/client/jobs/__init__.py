"""Client API for jobs in Nexus."""

import asyncio
import json
import ssl
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Type, Union, cast, overload
from uuid import UUID

import httpx
from quantinuum_schemas.models.backend_config import config_name_to_class
from quantinuum_schemas.models.hypertket_config import HyperTketConfig
from websockets.asyncio.client import connect, process_exception
from websockets.exceptions import ConnectionClosed

import qnexus.exceptions as qnx_exc
from qnexus.client import get_nexus_client
from qnexus.client.jobs import _compile, _execute
from qnexus.client.nexus_iterator import NexusIterator
from qnexus.client.utils import accept_circuits_for_programs, handle_fetch_errors
from qnexus.config import CONFIG
from qnexus.context import (
    get_active_project,
    merge_project_from_context,
    merge_properties_from_context,
    merge_scope_from_context,
)
from qnexus.models import BackendConfig
from qnexus.models.annotations import Annotations, PropertiesDict
from qnexus.models.filters import (
    CreatorFilter,
    JobStatusFilter,
    JobTypeFilter,
    NameFilter,
    PaginationFilter,
    ProjectRefFilter,
    PropertiesFilter,
    ScopeFilter,
    SortFilter,
    SortFilterEnum,
    TimeFilter,
)
from qnexus.models.job_status import WAITING_STATUS, JobStatus, JobStatusEnum
from qnexus.models.language import Language
from qnexus.models.references import (
    CircuitRef,
    CompilationResultRef,
    CompileJobRef,
    DataframableList,
    ExecuteJobRef,
    ExecutionProgram,
    ExecutionResult,
    ExecutionResultRef,
    GpuDecoderConfigRef,
    IncompleteJobItemRef,
    JobRef,
    JobType,
    ProjectRef,
    SystemRef,
    WasmModuleRef,
)

from qnexus.models.scope import ScopeFilterEnum
from qnexus.models.utils import assert_never

EPOCH_START = datetime(1970, 1, 1, tzinfo=timezone.utc)


class RemoteRetryStrategy(str, Enum):
    """Strategy to use when retrying jobs.

    Each strategy defines how the system should approach resolving
    potential conflicts with remote state.

    FULL_RESTART will act as though the job is entirely fresh and
    re-perform every action.
    """

    FULL_RESTART = "FULL_RESTART"


class Params(
    CreatorFilter,
    PropertiesFilter,
    PaginationFilter,
    NameFilter,
    JobStatusFilter,
    ProjectRefFilter,
    JobTypeFilter,
    ScopeFilter,
    SortFilter,
    TimeFilter,
):
    """Params for filtering jobs"""


@merge_scope_from_context
@merge_project_from_context
def get_all(
    *,
    name_like: str | None = None,
    name_exact: list[str] | None = None,
    creator_email: list[str] | None = None,
    project: ProjectRef | None = None,
    properties: PropertiesDict | None = None,
    job_status: list[JobStatusEnum] | None = None,
    job_type: list[JobType] | None = None,
    created_before: datetime | None = None,
    created_after: datetime | None = datetime(day=1, month=1, year=2023),
    modified_before: datetime | None = None,
    modified_after: datetime | None = None,
    sort_filters: list[SortFilterEnum] | None = None,
    page_number: int | None = None,
    page_size: int | None = None,
    scope: ScopeFilterEnum = ScopeFilterEnum.USER,
) -> NexusIterator[CompileJobRef | ExecuteJobRef]:
    """Get a NexusIterator over jobs with optional filters."""
    project = project or get_active_project(project_required=False)
    project = cast(ProjectRef, project)

    params = Params(
        name_like=name_like,
        name_exact=name_exact,
        creator_email=creator_email,
        project=project,
        status=(
            JobStatusFilter.convert_status_filters(job_status) if job_status else None
        ),
        job_type=job_type,
        properties=properties,
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
        resource_type="Job",
        nexus_url="/api/jobs/v1beta3",
        params=params,
        wrapper_method=_to_jobref,
        nexus_client=get_nexus_client(),
    )


def _to_jobref(data: dict[str, Any]) -> DataframableList[CompileJobRef | ExecuteJobRef]:
    """Parse a json dictionary into a list of JobRefs."""

    job_list: list[CompileJobRef | ExecuteJobRef] = []

    for entry in data["data"]:
        project_id = entry["relationships"]["project"]["data"]["id"]

        project_details = next(
            proj for proj in data["included"] if proj["id"] == project_id
        )
        project = ProjectRef(
            id=project_id,
            annotations=Annotations.from_dict(project_details["attributes"]),
            contents_modified=project_details["attributes"]["contents_modified"],
            archived=project_details["attributes"]["archived"],
        )

        system_id: str | None = (
            entry["relationships"]["system"]["data"]["id"]
            if "system" in entry["relationships"]
            else None
        )
        system_details = (
            next(item for item in data["included"] if item["id"] == system_id)
            if system_id is not None
            else None
        )

        system = (
            SystemRef(
                id=UUID(system_id),
                name=system_details["attributes"]["name"],
                provider_name=system_details["attributes"]["provider_name"],
            )
            if system_id is not None and system_details is not None
            else None
        )
        job_type: Type[CompileJobRef] | Type[ExecuteJobRef]
        match entry["attributes"]["job_type"]:
            case JobType.COMPILE:
                job_type = CompileJobRef
            case JobType.EXECUTE:
                job_type = ExecuteJobRef
            case _:
                assert_never(entry["attributes"]["job_type"])

        job_list.append(
            job_type(
                id=entry["id"],
                annotations=Annotations.from_dict(entry["attributes"]),
                job_type=entry["attributes"]["job_type"],
                last_status=JobStatus.from_dict(entry["attributes"]["status"]).status,
                last_message=JobStatus.from_dict(entry["attributes"]["status"]).message,
                last_status_detail=JobStatus.from_dict(entry["attributes"]["status"]),
                project=project,
                system=system,
            )
        )
    return DataframableList(job_list)


@merge_scope_from_context
def get(
    *,
    id: Union[str, UUID, None] = None,
    name: str | None = None,
    name_like: str | None = None,
    creator_email: list[str] | None = None,
    project: ProjectRef | None = None,
    properties: PropertiesDict | None = None,
    job_status: list[JobStatusEnum] | None = None,
    job_type: list[JobType] | None = None,
    created_before: datetime | None = None,
    created_after: datetime | None = datetime(day=1, month=1, year=2023),
    modified_before: datetime | None = None,
    modified_after: datetime | None = None,
    sort_filters: list[SortFilterEnum] | None = None,
    page_number: int | None = None,
    page_size: int | None = None,
    scope: ScopeFilterEnum = ScopeFilterEnum.USER,
) -> JobRef:
    """
    Get a single job using filters. Throws an exception if the filters do
    not match exactly one object.
    """
    if id:
        return _fetch_by_id(job_id=id, scope=scope)

    return get_all(
        name_like=name_like,
        name_exact=[name] if name else None,
        creator_email=creator_email,
        project=project,
        properties=properties,
        job_status=job_status,
        job_type=job_type,
        created_before=created_before,
        created_after=created_after,
        modified_before=modified_before,
        modified_after=modified_after,
        sort_filters=sort_filters,
        page_number=page_number,
        page_size=page_size,
        scope=scope,
    ).try_unique_match()


@merge_scope_from_context
def _fetch_by_id(
    job_id: UUID | str, scope: ScopeFilterEnum = ScopeFilterEnum.USER
) -> JobRef:
    """Utility method for fetching directly by a unique identifier."""
    params = Params(
        scope=scope,
    ).model_dump(by_alias=True, exclude_unset=True, exclude_none=True)

    res = get_nexus_client().get(f"/api/jobs/v1beta3/{job_id}", params=params)

    handle_fetch_errors(res)

    job_data = res.json()

    project_id = job_data["data"]["relationships"]["project"]["data"]["id"]
    project_details = next(
        proj for proj in job_data["included"] if proj["id"] == project_id
    )
    project = ProjectRef(
        id=project_id,
        annotations=Annotations.from_dict(project_details["attributes"]),
        contents_modified=project_details["attributes"]["contents_modified"],
        archived=project_details["attributes"]["archived"],
    )

    system_id: str | None = (
        job_data["data"]["relationships"]["system"]["data"]["id"]
        if "system" in job_data["data"]["relationships"]
        else None
    )

    system_details = (
        next(item for item in job_data["included"] if item["id"] == system_id)
        if system_id is not None
        else None
    )

    system = (
        SystemRef(
            id=UUID(system_id),
            name=system_details["attributes"]["name"],
            provider_name=system_details["attributes"]["provider_name"],
        )
        if system_id is not None and system_details is not None
        else None
    )

    job_type: Type[CompileJobRef] | Type[ExecuteJobRef]
    match job_data["data"]["attributes"]["job_type"]:
        case JobType.COMPILE:
            job_type = CompileJobRef
        case JobType.EXECUTE:
            job_type = ExecuteJobRef
        case _:
            assert_never(job_data["attributes"]["job_type"])

    backend_config_dict = job_data["data"]["attributes"]["definition"]["backend_config"]
    backend_config_class = config_name_to_class[backend_config_dict["type"]]
    backend_config: BackendConfig = backend_config_class(  # type: ignore
        **backend_config_dict
    )

    return job_type(
        id=job_data["data"]["id"],
        annotations=Annotations.from_dict(job_data["data"]["attributes"]),
        job_type=job_data["data"]["attributes"]["job_type"],
        last_status=JobStatus.from_dict(
            job_data["data"]["attributes"]["status"]
        ).status,
        last_message=JobStatus.from_dict(
            job_data["data"]["attributes"]["status"]
        ).message,
        last_status_detail=JobStatus.from_dict(
            job_data["data"]["attributes"]["status"]
        ),
        project=project,
        backend_config_store=backend_config,
        system=system,
    )


def wait_for(
    job: JobRef,
    wait_for_status: JobStatusEnum = JobStatusEnum.COMPLETED,
    timeout: float | None = 900.0,
) -> JobStatus:
    """Check job status until the job is complete (or a specified status)."""
    job_status = asyncio.run(
        asyncio.wait_for(
            listen_job_status(job=job, wait_for_status=wait_for_status),
            timeout=timeout,
        )
    )

    if (
        job_status.status == JobStatusEnum.ERROR
        and wait_for_status != JobStatusEnum.ERROR
    ):
        raise qnx_exc.JobError(f"Job errored with detail: {job_status.error_detail}")
    if (
        job_status.status == JobStatusEnum.CANCELLED
        and wait_for_status != JobStatusEnum.CANCELLED
    ):
        raise qnx_exc.JobError("Job was cancelled")
    if (
        job_status.status == JobStatusEnum.DEPLETED
        and wait_for_status != JobStatusEnum.DEPLETED
    ):
        raise qnx_exc.JobError("Job has run out of account credits")
    if (
        job_status.status == JobStatusEnum.TERMINATED
        and wait_for_status != JobStatusEnum.TERMINATED
    ):
        raise qnx_exc.JobError("Job has been terminated")

    return job_status


@merge_scope_from_context
def status(job: JobRef, scope: ScopeFilterEnum = ScopeFilterEnum.USER) -> JobStatus:
    """Get the status of a job."""
    resp = get_nexus_client().get(
        f"api/jobs/v1beta3/{job.id}/attributes/status",
        params={"scope": scope.value},
    )
    if resp.status_code != 200:
        raise qnx_exc.ResourceFetchFailed(
            message=resp.text, status_code=resp.status_code
        )
    job_status = JobStatus.from_dict(resp.json())
    # job.last_status = job_status.status
    return job_status


async def listen_job_status(
    job: JobRef, wait_for_status: JobStatusEnum = JobStatusEnum.COMPLETED
) -> JobStatus:
    """Check the Status of a Job via a websocket connection.
    Will use SSO tokens."""
    job_status = status(job)
    # logger.debug("Current job status: %s", job_status.status)
    if job_status.status not in WAITING_STATUS or job_status.status == wait_for_status:
        return job_status

    ssl_context = httpx.create_ssl_context(verify=CONFIG.httpx_verify)

    def _process_exception(exc: Exception) -> Exception | None:
        """Utility wrapper around process_exception that tells the websockets
        library not to auto-retry SSLErrors as they are usually not recoverable.

        Unfortunately SSLError inherits from OSError which websockets will always
        retried when `connect` is used in an async for loop.
        """
        if isinstance(exc, ssl.SSLError):
            return exc
        return process_exception(exc)

    additional_headers = {
        # TODO, this cookie will expire frequently
        "Cookie": f"myqos_id={get_nexus_client().auth.cookies.get('myqos_id')}"  # type: ignore
    }
    async for websocket in connect(
        f"{CONFIG.websockets_url}/api/jobs/v1beta3/{job.id}/attributes/status/ws",
        ssl=ssl_context,
        additional_headers=additional_headers,
        process_exception=_process_exception,
        # logger=logger,
    ):
        try:
            async for status_json in websocket:
                # logger.debug("New status: %s", status_json)
                job_status = JobStatus.from_dict(json.loads(status_json))

                if (
                    job_status.status not in WAITING_STATUS
                    or job_status.status == wait_for_status
                ):
                    break
            break
        except ConnectionClosed:
            # logger.debug(
            #     "Websocket connection closed... attempting to reconnect..."
            # )
            continue
        finally:
            try:
                await websocket.close(code=1000, reason="Client closed connection")
            except GeneratorExit:
                pass

    return job_status


@merge_scope_from_context
@overload
def results(
    job: CompileJobRef,
    allow_incomplete: bool = False,
    scope: ScopeFilterEnum = ScopeFilterEnum.USER,
) -> DataframableList[CompilationResultRef | IncompleteJobItemRef]: ...


@merge_scope_from_context
@overload
def results(
    job: ExecuteJobRef,
    allow_incomplete: bool = False,
    scope: ScopeFilterEnum = ScopeFilterEnum.USER,
) -> DataframableList[ExecutionResultRef | IncompleteJobItemRef]: ...


@merge_scope_from_context
def results(
    job: CompileJobRef | ExecuteJobRef,
    allow_incomplete: bool = False,
    scope: ScopeFilterEnum = ScopeFilterEnum.USER,
) -> (
    DataframableList[CompilationResultRef | IncompleteJobItemRef]
    | DataframableList[ExecutionResultRef | IncompleteJobItemRef]
):
    """Get the ResultRefs from a JobRef, if the job is complete.
    To enable fetching results from Jobs with incomplete items, set allow_incomplete=True.
    """
    match job:
        case CompileJobRef():
            return _compile._results(job, allow_incomplete, scope)
        case ExecuteJobRef():
            return _execute._results(job, allow_incomplete, scope)
        case _:
            assert_never(job.job_type)


def retry_submission(
    job: JobRef,
    retry_status: list[JobStatusEnum] | None = None,
    remote_retry_strategy: RemoteRetryStrategy = RemoteRetryStrategy.FULL_RESTART,
    user_group: str | None = None,
) -> None:
    """Retry a job in Nexus according to status(es) or retry strategy.

    By default, jobs with the ERROR status will be retried.
    """
    body: dict[str, str | list[str]] = {"remote_retry_strategy": remote_retry_strategy}

    if user_group is not None:
        body["user_group"] = user_group

    if retry_status is not None:
        body["retry_status"] = [status.name for status in retry_status]

    res = get_nexus_client().post(
        f"/api/jobs/v1beta3/{job.id}/rpc/retry",
        json=body,
    )
    if res.status_code != 202:
        res.raise_for_status()


@merge_scope_from_context
def cancel(job: JobRef, scope: ScopeFilterEnum = ScopeFilterEnum.USER) -> None:
    """Attempt cancellation of a job in Nexus.

    If the job has been submitted to a backend, Nexus will request cancellation of the job.
    """
    res = get_nexus_client().post(
        f"/api/jobs/v1beta3/{job.id}/rpc/cancel",
        json={},
        params={"scope": scope.value},
    )

    if res.status_code != 202:
        res.raise_for_status()


@merge_scope_from_context
def delete(job: JobRef, scope: ScopeFilterEnum = ScopeFilterEnum.USER) -> None:
    """Delete a job in Nexus."""
    res = get_nexus_client().delete(
        f"/api/jobs/v1beta3/{job.id}",
        params={"scope": scope.value},
    )

    if res.status_code != 204:
        res.raise_for_status()


@accept_circuits_for_programs
@merge_properties_from_context
def compile(
    programs: Union[CircuitRef, list[CircuitRef]],
    backend_config: BackendConfig,
    name: str,
    description: str = "",
    project: ProjectRef | None = None,
    properties: PropertiesDict | None = None,
    optimisation_level: int = 2,
    credential_name: str | None = None,
    user_group: str | None = None,
    hypertket_config: HyperTketConfig | None = None,
    timeout: float | None = 300.0,
) -> DataframableList[CircuitRef]:
    """
    Utility method to run a compile job on a program or programs and return a
    DataframableList of the compiled programs.
    """
    project = project or get_active_project(project_required=True)
    project = cast(ProjectRef, project)

    compile_job_ref = _compile.start_compile_job(
        programs=programs,
        backend_config=backend_config,
        name=name,
        description=description,
        project=project,
        properties=properties,
        optimisation_level=optimisation_level,
        credential_name=credential_name,
        user_group=user_group,
        hypertket_config=hypertket_config,
    )

    wait_for(job=compile_job_ref, timeout=timeout)

    compile_results = results(compile_job_ref)

    compiled_circuits: list[CircuitRef] = []
    for compile_result in compile_results:
        if isinstance(compile_result, CompilationResultRef):
            compiled_circuits.append(compile_result.get_output())
        elif isinstance(compile_result, IncompleteJobItemRef):
            raise qnx_exc.ResourceFetchFailed(
                f"Compile job item {compile_result.job_item_integer_id} is in status {compile_result.last_status}"
            )
        else:
            assert_never(compile_result)

    return DataframableList(compiled_circuits)


@accept_circuits_for_programs
@merge_properties_from_context
def execute(
    programs: Union[ExecutionProgram, list[ExecutionProgram]],
    n_shots: list[int] | list[None],
    backend_config: BackendConfig,
    name: str,
    description: str = "",
    properties: PropertiesDict | None = None,
    project: ProjectRef | None = None,
    valid_check: bool = True,
    wasm_module: WasmModuleRef | None = None,
    gpu_decoder_config: GpuDecoderConfigRef | None = None,
    language: Language = Language.AUTO,
    credential_name: str | None = None,
    user_group: str | None = None,
    timeout: float | None = 300.0,
) -> list[ExecutionResult]:
    """
    Utility method to run an execute job and return the results. Blocks until
    the results are available. See ``qnexus.start_execute_job`` for a function
    that submits the job and returns immediately, rather than waiting for
    results.
    """

    execute_job_ref = _execute.start_execute_job(
        programs=programs,
        n_shots=n_shots,
        backend_config=backend_config,
        name=name,
        description=description,
        properties=properties,
        project=project,
        valid_check=valid_check,
        wasm_module=wasm_module,
        gpu_decoder_config=gpu_decoder_config,
        language=language,
        credential_name=credential_name,
        user_group=user_group,
    )

    wait_for(job=execute_job_ref, timeout=timeout)

    execute_results = results(execute_job_ref)

    ex_results: list[ExecutionResult] = []
    for result in execute_results:
        if isinstance(result, ExecutionResultRef):
            ex_results.append(result.download_result())
        elif isinstance(result, IncompleteJobItemRef):
            raise qnx_exc.ResourceFetchFailed(
                f"Compile job item {result.job_item_integer_id} is in status {result.last_status}"
            )
        else:
            assert_never(result)

    return ex_results


@merge_scope_from_context
def cost(
    job: CompileJobRef | ExecuteJobRef, scope: ScopeFilterEnum = ScopeFilterEnum.USER
) -> float:
    """Get the HQC cost of a job from a JobRef."""

    resp = get_nexus_client().get(
        f"/api/jobs/v1beta3/{job.id}",
        params={"scope": scope.value},
    )
    if resp.status_code != 200:
        raise qnx_exc.ResourceFetchFailed(
            message=resp.text, status_code=resp.status_code
        )
    resp_data = resp.json()["data"]
    job_status = resp_data["attributes"]["status"]
    cost = job_status.get("cost")
    return float(cost) if cost is not None else 0.0


@merge_scope_from_context
def cost_confidence(
    job: CompileJobRef | ExecuteJobRef, scope: ScopeFilterEnum = ScopeFilterEnum.USER
) -> list[tuple[float, float]]:
    """
    Get the HQC cost and confidence of a job from a JobRef.

    Returns a list of tuples of (cost, confidence) for each job item.
    """
    resp = get_nexus_client().get(
        f"/api/jobs/v1beta3/{job.id}", params={"scope": scope.value}
    )
    if resp.status_code != 200:
        raise qnx_exc.ResourceFetchFailed(
            message=resp.text, status_code=resp.status_code
        )

    # Loop over all items from the API and gather cost_confidence_items
    resp_data = resp.json()["data"]
    items = resp_data["attributes"]["definition"]["items"]
    cost_confidence_items = []
    for i, item in enumerate(items):
        cost_confidence_items.append(
            (
                float(item["status"].get("cost", 0.0)),
                float(item["status"].get("cost_confidence", -1.0)),
            )
        )

    return cost_confidence_items
