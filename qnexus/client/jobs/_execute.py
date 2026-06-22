"""Client API for execution in Nexus."""

from typing import Union, cast

from hugr.qsystem.result import QsysResult
from pytket.backends.backendinfo import BackendInfo
from pytket.backends.backendresult import BackendResult

import qnexus.exceptions as qnx_exc
from qnexus.client import get_nexus_client
from qnexus.client.results import (
    fetch_pytket_execution_result_by_id,
    fetch_qsys_result_by_id,
)
from qnexus.client.utils import accept_circuits_for_programs
from qnexus.context import (
    get_active_project,
    merge_properties_from_context,
    merge_scope_from_context,
    merge_target_region_from_context,
)
from qnexus.models import BackendConfig
from qnexus.models.annotations import Annotations, CreateAnnotations, PropertiesDict
from qnexus.models.job_status import JobStatus, JobStatusEnum
from qnexus.models.language import Language
from qnexus.models.references import (
    CircuitRef,
    DataframableList,
    ExecuteJobRef,
    ExecutionProgram,
    ExecutionResultRef,
    GpuDecoderConfigRef,
    HUGRRef,
    IncompleteJobItemRef,
    JobType,
    ProjectRef,
    QIRRef,
    QIRResult,
    ResultType,
    ResultVersions,
    WasmModuleRef,
)
from qnexus.models.region import Region
from qnexus.models.scope import ScopeFilterEnum
from qnexus.models.utils import assert_never, truncate_to_2dp


@accept_circuits_for_programs
@merge_properties_from_context
@merge_target_region_from_context
def start_execute_job(
    programs: ExecutionProgram | list[ExecutionProgram],
    n_shots: int | list[int] | list[None],
    backend_config: BackendConfig,
    name: str,
    description: str = "",
    properties: PropertiesDict | None = None,
    project: ProjectRef | None = None,
    valid_check: bool = True,
    language: Language = Language.AUTO,
    credential_name: str | None = None,
    wasm_module: WasmModuleRef | None = None,
    gpu_decoder_config: GpuDecoderConfigRef | None = None,
    user_group: str | None = None,
    target_region: Region | None = None,
    max_cost: float | list[float] | list[None] = list(),
    n_qubits: int | list[int] | list[None] = list(),
) -> ExecuteJobRef:
    """
    Submit an execute job to be run in Nexus. Returns an ``ExecuteJobRef``
    object which can be used to check the job's status.  See ``qnexus.execute``
    for a utility method that waits for the results and returns them.

    Examples:
        >>> import qnexus as qnx
        >>> execute_job_ref = qnx.jobs.execute(
        ...     programs=hugr_ref,
        ...     n_shots=1000,
        ...     backend_config=qnx.models.HeliosConfig(system_name="Helios-1"),
        ...     name="my-execute-job",
        ...     max_cost=10.0,
        ... )
    """
    project = project or get_active_project(project_required=True)
    project = cast(ProjectRef, project)

    program_ids = (
        [str(p.id) for p in programs]
        if isinstance(programs, list)
        else [str(programs.id)]
    )

    if isinstance(n_shots, int):
        n_shots = [n_shots] * len(program_ids)
    if isinstance(max_cost, (int, float)):
        max_cost = [float(max_cost)] * len(program_ids)
    elif not max_cost:
        max_cost = [None] * len(program_ids)
    if isinstance(n_qubits, int):
        n_qubits = [n_qubits] * len(program_ids)
    elif not n_qubits:
        n_qubits = [None] * len(program_ids)

    if len(n_shots) != len(program_ids):
        raise ValueError("Number of programs must equal number of n_shots.")
    if len(max_cost) != len(program_ids):
        raise ValueError("Number of programs must equal number of max_cost.")
    if len(n_qubits) != len(program_ids):
        raise ValueError("Number of programs must equal number of n_qubits.")

    attributes_dict = CreateAnnotations(
        name=name,
        description=description,
        properties=properties,
    ).model_dump(exclude_none=True)

    items = [
        {
            "program_id": program_id,
            "n_shots": n_shot,
            **({"max_cost": mc} if mc is not None else {}),
            **({"n_qubits": nq} if nq is not None else {}),
        }
        for program_id, n_shot, mc, nq in zip(program_ids, n_shots, max_cost, n_qubits)
    ]

    attributes_dict.update(
        {
            "job_type": "execute",
            "definition": {
                "job_definition_type": "execute_job_definition",
                "backend_config": backend_config.model_dump(
                    exclude_none=True, mode="json"
                ),
                "user_group": user_group,
                "target_region": target_region,
                "valid_check": valid_check,
                "language": (
                    language.value if isinstance(language, Language) else language
                ),
                "wasm_module_id": str(wasm_module.id) if wasm_module else None,
                "gpu_decoder_config_id": (
                    str(gpu_decoder_config.id) if gpu_decoder_config else None
                ),
                "credential_name": credential_name,
                "items": items,
            },
        }
    )
    relationships = {
        "project": {"data": {"id": str(project.id), "type": "project"}},
    }
    req_dict = {
        "data": {
            "attributes": attributes_dict,
            "relationships": relationships,
            "type": "job",
        }
    }

    resp = get_nexus_client().post(
        "/api/jobs/v1beta3",
        json=req_dict,
    )
    if resp.status_code != 202:
        raise qnx_exc.ResourceCreateFailed(
            message=resp.text, status_code=resp.status_code
        )

    return ExecuteJobRef(
        id=resp.json()["data"]["id"],
        annotations=Annotations.from_dict(resp.json()["data"]["attributes"]),
        job_type=JobType.EXECUTE,
        last_status=JobStatusEnum.SUBMITTED,
        last_message="",
        last_status_detail=JobStatus.from_dict(
            resp.json()["data"]["attributes"]["status"]
        ),
        project=project,
        backend_config_store=backend_config,
    )


@merge_scope_from_context
def _results(
    execute_job: ExecuteJobRef,
    allow_incomplete: bool = True,
    scope: ScopeFilterEnum = ScopeFilterEnum.USER,
) -> DataframableList[ExecutionResultRef | IncompleteJobItemRef]:
    """Get the results from an execute job."""

    resp = get_nexus_client().get(
        f"/api/jobs/v1beta3/{execute_job.id}",
        params={"scope": scope.value},
    )
    if resp.status_code != 200:
        raise qnx_exc.ResourceFetchFailed(
            message=resp.text, status_code=resp.status_code
        )
    resp_data = resp.json()["data"]
    job_status = resp_data["attributes"]["status"]["status"]

    if job_status != "COMPLETED" and allow_incomplete is not True:
        raise qnx_exc.ResourceFetchFailed(message=f"Job status: {job_status}")

    execute_results: DataframableList[ExecutionResultRef | IncompleteJobItemRef] = (
        DataframableList([])
    )

    program_types = resp_data["relationships"]["programs"]["data"]
    program_type_dict = {p["id"]: p["type"] for p in program_types}

    for item in resp_data["attributes"]["definition"]["items"]:
        result_type: ResultType | None = None

        match item.get("result_type", None):
            case ResultType.QSYS:
                result_type = ResultType.QSYS
            case ResultType.PYTKET:
                result_type = ResultType.PYTKET
            case None:
                result_type = None
            case _:
                assert_never(item["result_type"])

        # Check if item is in a state that returns results
        # and has results
        if (
            item["status"]["status"]
            in (
                "CANCELLED",
                "ERROR",
                "DEPLETED",
                "TERMINATED",
                "COMPLETED",
                "RUNNING",
                "QUEUED",
            )
            and result_type
        ):
            result_ref = ExecutionResultRef(
                id=item["result_id"],
                job_item_id=item.get("external_handle", None),
                job_item_integer_id=item.get("item_id", None),
                annotations=execute_job.annotations,
                project=execute_job.project,
                result_type=result_type,
                cost=truncate_to_2dp(item["status"].get("cost", None)),
                last_status_detail=JobStatus.from_dict(item["status"]),
            )

            execute_results.append(result_ref)

        elif allow_incomplete is True:
            # Job item is not complete, return an IncompleteJobItemRef
            program_id = item.get("program_id", None)
            program_type = program_type_dict[program_id]

            incomplete_ref = IncompleteJobItemRef(
                job_item_id=item.get("external_handle", None),
                job_item_integer_id=item.get("item_id", None),
                annotations=execute_job.annotations,
                project=execute_job.project,
                program_type=program_type,
                program_id=program_id,
                job_type=JobType.EXECUTE,
                last_status=JobStatusEnum[item["status"]["status"]],
                last_message=item["status"].get("message", ""),
                last_status_detail=JobStatus.from_dict(item["status"]),
            )
            execute_results.append(incomplete_ref)

    return execute_results


@merge_scope_from_context
def _fetch_pytket_execution_result(
    result_ref: ExecutionResultRef,
    scope: ScopeFilterEnum = ScopeFilterEnum.USER,
) -> tuple[BackendResult, BackendInfo, Union[CircuitRef, QIRRef]]:
    """Get the results for an execute job item."""
    assert result_ref.result_type == ResultType.PYTKET, "Incorrect result type"

    return fetch_pytket_execution_result_by_id(result_ref.id, scope)


@merge_scope_from_context
def _fetch_qsys_execution_result(
    result_ref: ExecutionResultRef,
    version: ResultVersions,
    scope: ScopeFilterEnum = ScopeFilterEnum.USER,
) -> tuple[QsysResult | QIRResult, BackendInfo, HUGRRef | QIRRef]:
    """Get the results of a next-gen Qsys execute job."""
    assert result_ref.result_type == ResultType.QSYS, "Incorrect result type"

    return fetch_qsys_result_by_id(result_ref.id, version, scope)
