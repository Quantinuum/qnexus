"""Client API for execution in Nexus."""

from typing import Union, cast

from hugr.qsystem.result import QsysResult
from pytket.backends.backendinfo import BackendInfo
from pytket.backends.backendresult import BackendResult

import qnexus.exceptions as qnx_exc
from qnexus.client import circuits as circuit_api
from qnexus.client import get_nexus_client
from qnexus.client import hugr as hugr_api
from qnexus.client import qir as qir_api
from qnexus.client.utils import accept_circuits_for_programs
from qnexus.context import (
    get_active_project,
    merge_properties_from_context,
    merge_scope_from_context,
)
from qnexus.models import BackendConfig, StoredBackendInfo, to_pytket_backend_info
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
from qnexus.models.scope import ScopeFilterEnum
from qnexus.models.utils import assert_never, truncate_to_2dp


@accept_circuits_for_programs
@merge_properties_from_context
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
    max_cost: float | list[float] | list[None] = list(), 
    n_qubits: int | list[int] | list[None] = list(),
) -> ExecuteJobRef:
    """
    Submit an execute job to be run in Nexus. Returns an ``ExecuteJobRef``
    object which can be used to check the job's status.  See ``qnexus.execute``
    for a utility method that waits for the results and returns them.
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
                "backend_config": backend_config.model_dump(exclude_none=True),
                "user_group": user_group,
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
        project=project,
        backend_config_store=backend_config,
    )


@merge_scope_from_context
def _results(
    execute_job: ExecuteJobRef,
    allow_incomplete: bool = False,
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
            incomplete_ref = IncompleteJobItemRef(
                job_item_id=item.get("external_handle", None),
                job_item_integer_id=item.get("item_id", None),
                annotations=execute_job.annotations,
                project=execute_job.project,
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

    res = get_nexus_client().get(
        f"/api/results/v1beta3/{result_ref.id}",
        params={"scope": scope.value},
    )
    if res.status_code != 200:
        raise qnx_exc.ResourceFetchFailed(message=res.text, status_code=res.status_code)

    res_dict = res.json()
    program_data = res_dict["data"]["relationships"]["program"]["data"]
    program_id = program_data["id"]
    program_type = program_data["type"]

    input_program: CircuitRef | QIRRef
    match program_type:
        case "circuit":
            input_program = circuit_api._fetch_by_id(program_id)
        case "qir":
            input_program = qir_api._fetch_by_id(program_id)
        case _:
            raise ValueError(f"Unknown program type {type}")

    results_data = res_dict["data"]["attributes"]

    results_dict = {k: v for k, v in results_data.items() if v != [] and v is not None}

    backend_result = BackendResult.from_dict(results_dict)

    backend_info_data = next(
        data for data in res_dict["included"] if data["type"] == "backend_snapshot"
    )
    backend_info = to_pytket_backend_info(
        StoredBackendInfo(**backend_info_data["attributes"])
    )

    return (backend_result, backend_info, input_program)


@merge_scope_from_context
def _fetch_qsys_execution_result(
    result_ref: ExecutionResultRef,
    version: ResultVersions,
    scope: ScopeFilterEnum = ScopeFilterEnum.USER,
) -> tuple[QsysResult | QIRResult, BackendInfo, HUGRRef | QIRRef]:
    """Get the results of a next-gen Qsys execute job."""
    assert result_ref.result_type == ResultType.QSYS, "Incorrect result type"

    chunk_number = 0
    params = {
        "version": version.value,
        "chunk_number": chunk_number,
        "scope": scope.value,
    }

    res = get_nexus_client().get(
        f"/api/qsys_results/v1beta2/partial/{result_ref.id}", params=params
    )

    if res.status_code != 200:
        raise qnx_exc.ResourceFetchFailed(message=res.text, status_code=res.status_code)

    # This is only needed to be set once, as subsequent calls will
    # return the same information for the relationships.
    res_dict = res.json()
    input_program_id = res_dict["data"]["relationships"]["program"]["data"]["id"]

    input_program: HUGRRef | QIRRef
    result: QsysResult | QIRResult
    match res_dict["data"]["relationships"]["program"]["data"]["type"]:
        case "hugr":
            input_program = hugr_api._fetch_by_id(
                input_program_id,
            )
            result = QsysResult(res_dict["data"]["attributes"].get("results"))
        case "qir":
            input_program = qir_api._fetch_by_id(
                input_program_id,
            )
            if version == ResultVersions.DEFAULT:
                result = QIRResult(res_dict["data"]["attributes"].get("results"))
            else:
                result = QsysResult(res_dict["data"]["attributes"].get("results"))

    backend_info_data = next(
        data for data in res_dict["included"] if data["type"] == "backend_snapshot"
    )
    backend_info = to_pytket_backend_info(
        StoredBackendInfo(**backend_info_data["attributes"])
    )

    # We shouldn't be doing infinite loops, but the API currently doesn't
    # provide a way to know how many chunks there are, so we loop until we
    # get all of them.
    while True:
        chunk_number += 1
        params["chunk_number"] = chunk_number
        partial = get_nexus_client().get(
            f"/api/qsys_results/v1beta2/partial/{result_ref.id}", params=params
        )
        if partial.status_code == 404:
            # No more chunks. Stop here.
            break
        if partial.status_code != 200:
            raise qnx_exc.ResourceFetchFailed(
                message=res.text, status_code=partial.status_code
            )
        if isinstance(result.results, str):
            assert (
                version == ResultVersions.DEFAULT
            )  # Only QIR outputs are in this mode
            prev_str = result.results.split("END")[
                0
            ]  # remove the end tag from result.results
            next_str = "\n".join(
                [
                    line
                    for line in QIRResult(
                        partial.json()["data"]["attributes"]["results"]
                    ).results.splitlines()
                    if "OUTPUT" in line
                ]
            )  # just the output lines
            result.results += (
                prev_str + next_str + "END\t0\n"
            )  # join everything back up
        else:
            next_res = QsysResult(partial.json()["data"]["attributes"]["results"])
            result.results.extend(next_res.results)

    return (
        result,
        backend_info,
        input_program,
    )
