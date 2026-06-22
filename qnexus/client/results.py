"""Client API for results in Nexus."""

# https://staging.myqos.com/api-docs#/results


# def get():
#     pass


# def get_only():
#     pass

from uuid import UUID

from hugr.qsystem.result import QsysResult
from pytket.backends.backendinfo import BackendInfo
from pytket.backends.backendresult import BackendResult

import qnexus.exceptions as qnx_exc
from qnexus.client import circuits as circuit_api
from qnexus.client import get_nexus_client
from qnexus.client import hugr as hugr_api
from qnexus.client import qir as qir_api
from qnexus.context import merge_scope_from_context
from qnexus.models import StoredBackendInfo, to_pytket_backend_info
from qnexus.models.references import (
    CircuitRef,
    HUGRRef,
    QIRRef,
    QIRResult,
    ResultVersions,
)
from qnexus.models.scope import ScopeFilterEnum


@merge_scope_from_context
def get(
    id: UUID, scope: ScopeFilterEnum = ScopeFilterEnum.USER
) -> tuple[
    BackendResult | QsysResult | QIRResult, BackendInfo, CircuitRef | QIRRef | HUGRRef
]:
    """Fetch an execution job result directly, using the ID."""
    res: tuple[
        BackendResult | QsysResult | QIRResult,
        BackendInfo,
        CircuitRef | QIRRef | HUGRRef,
    ]
    try:  # try classical result
        res = fetch_pytket_execution_result_by_id(id, scope)
    except qnx_exc.ResourceFetchFailed as ex:
        if ex.status_code == 404:  # if status is not found, try qsys
            res = fetch_qsys_result_by_id(id, ResultVersions.DEFAULT, scope)
        else:
            raise ex
    return res


def fetch_pytket_execution_result_by_id(
    id: UUID, scope: ScopeFilterEnum = ScopeFilterEnum.USER
) -> tuple[BackendResult, BackendInfo, CircuitRef | QIRRef]:
    """Fetch a Pytket result directly using the ID."""
    res = get_nexus_client().get(
        f"/api/results/v1beta3/{id}",
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


def fetch_qsys_result_by_id(
    id: UUID,
    version: ResultVersions,
    scope: ScopeFilterEnum = ScopeFilterEnum.USER,
) -> tuple[QsysResult | QIRResult, BackendInfo, HUGRRef | QIRRef]:
    """Fetch a Qsys result directly using the ID."""
    chunk_number = 0
    params = {
        "version": version.value,
        "chunk_number": chunk_number,
        "scope": scope.value,
    }

    res = get_nexus_client().get(
        f"/api/qsys_results/v1beta2/partial/{id}", params=params
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
            f"/api/qsys_results/v1beta2/partial/{id}", params=params
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
