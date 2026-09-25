import uuid
from datetime import datetime
from unittest import mock

import pytest
from hugr.qsystem.result import QsysResult
from pytket.backends.backendinfo import BackendInfo
from pytket.backends.backendresult import BackendResult

from qnexus.client import roles, teams, users
from qnexus.client.jobs import _execute
from qnexus.context import using_scope
from qnexus.models import Role
from qnexus.models.annotations import Annotations
from qnexus.models.references import (
    CircuitRef,
    ExecutionProgram,
    ExecutionResult,
    ExecutionResultRef,
    HUGRRef,
    ProgramType,
    ProjectRef,
    QIRRef,
    QIRResult,
    ResultType,
    ResultVersions,
    TeamRef,
    UserRef,
)
from qnexus.models.scope import ScopeFilterEnum


def _project_ref() -> ProjectRef:
    return ProjectRef(
        id=uuid.uuid4(),
        annotations=Annotations(),
        contents_modified=datetime.now(),
    )


def _circuit_ref() -> CircuitRef:
    return CircuitRef(
        id=uuid.uuid4(), annotations=Annotations(), project=_project_ref()
    )


def _hugr_ref() -> HUGRRef:
    return HUGRRef(id=uuid.uuid4(), annotations=Annotations(), project=_project_ref())


def _qir_ref() -> QIRRef:
    return QIRRef(id=uuid.uuid4(), annotations=Annotations(), project=_project_ref())


def _execution_result_ref(
    result_type: ResultType = ResultType.PYTKET,
) -> ExecutionResultRef:
    return ExecutionResultRef(
        id=uuid.uuid4(),
        annotations=Annotations(),
        project=_project_ref(),
        result_type=result_type,
    )


def _program_ref(program_type: ProgramType) -> ExecutionProgram:
    match program_type:
        case ProgramType.CIRCUIT:
            return _circuit_ref()
        case ProgramType.HUGR:
            return _hugr_ref()
        case ProgramType.QIR:
            return _qir_ref()


def _fetched_result(
    result_type: ResultType,
    program_type: ProgramType,
    version: ResultVersions = ResultVersions.DEFAULT,
) -> tuple[ExecutionResult, BackendInfo, ExecutionProgram]:
    program = _program_ref(program_type)

    match result_type:
        case ResultType.PYTKET:
            if program_type not in (ProgramType.CIRCUIT, ProgramType.QIR):
                raise ValueError("Pytket results require a Circuit or QIR program")
            result: ExecutionResult = BackendResult()
        case ResultType.QSYS:
            if program_type not in (ProgramType.HUGR, ProgramType.QIR):
                raise ValueError("Qsys results require a HUGR or QIR program")
            result = (
                QIRResult("")
                if program_type == ProgramType.QIR and version == ResultVersions.DEFAULT
                else QsysResult([])
            )

    return result, mock.MagicMock(spec=BackendInfo), program


def _role() -> Role:
    return Role(
        id=uuid.uuid4(),
        name="Reader",
        description="Can read the resource",
        permissions="READ",
    )


DEFAULT_RESULT_CASES = [
    pytest.param(ResultType.PYTKET, ProgramType.CIRCUIT, id="pytket-circuit"),
    pytest.param(ResultType.PYTKET, ProgramType.QIR, id="pytket-qir"),
    pytest.param(ResultType.QSYS, ProgramType.HUGR, id="qsys-hugr"),
    pytest.param(ResultType.QSYS, ProgramType.QIR, id="qsys-qir"),
]


def _fetch_name(result_type: ResultType) -> str:
    return (
        "_fetch_pytket_execution_result"
        if result_type == ResultType.PYTKET
        else "_fetch_qsys_execution_result"
    )


def _assert_fetch_called_with_scope(
    fetch: mock.MagicMock,
    result_ref: ExecutionResultRef,
    result_type: ResultType,
    version: ResultVersions,
    scope: ScopeFilterEnum,
) -> None:
    if result_type == ResultType.PYTKET:
        fetch.assert_called_once_with(result_ref, scope=scope)
    else:
        fetch.assert_called_once_with(result_ref, version, scope=scope)


@pytest.mark.parametrize("result_type,program_type", DEFAULT_RESULT_CASES)
@pytest.mark.parametrize("explicit_scope", [None, ScopeFilterEnum.GLOBAL_ADMIN])
def test_execution_result_get_input_propagates_scope(
    explicit_scope: ScopeFilterEnum | None,
    result_type: ResultType,
    program_type: ProgramType,
) -> None:
    result_ref = _execution_result_ref(result_type)
    fetched = _fetched_result(result_type, program_type)
    context_scope = ScopeFilterEnum.ORG_ADMIN
    expected_scope = explicit_scope or context_scope

    with mock.patch.object(
        _execute, _fetch_name(result_type), return_value=fetched
    ) as fetch:
        with using_scope(context_scope):
            input_program = (
                result_ref.get_input()
                if explicit_scope is None
                else result_ref.get_input(scope=explicit_scope)
            )

    assert input_program == fetched[2]
    _assert_fetch_called_with_scope(
        fetch,
        result_ref,
        result_type,
        ResultVersions.DEFAULT,
        expected_scope,
    )


@pytest.mark.parametrize(
    "result_type,program_type,version",
    [
        pytest.param(
            ResultType.PYTKET,
            ProgramType.CIRCUIT,
            ResultVersions.DEFAULT,
            id="pytket-circuit",
        ),
        pytest.param(
            ResultType.PYTKET,
            ProgramType.QIR,
            ResultVersions.DEFAULT,
            id="pytket-qir",
        ),
        pytest.param(
            ResultType.QSYS,
            ProgramType.HUGR,
            ResultVersions.RAW,
            id="qsys-hugr-raw",
        ),
        pytest.param(
            ResultType.QSYS,
            ProgramType.QIR,
            ResultVersions.DEFAULT,
            id="qsys-qir-default",
        ),
    ],
)
@pytest.mark.parametrize("explicit_scope", [None, ScopeFilterEnum.GLOBAL_ADMIN])
def test_execution_result_download_result_propagates_scope(
    explicit_scope: ScopeFilterEnum | None,
    result_type: ResultType,
    program_type: ProgramType,
    version: ResultVersions,
) -> None:
    result_ref = _execution_result_ref(result_type)
    fetched = _fetched_result(result_type, program_type, version)
    context_scope = ScopeFilterEnum.ORG_ADMIN
    expected_scope = explicit_scope or context_scope

    with mock.patch.object(
        _execute, _fetch_name(result_type), return_value=fetched
    ) as fetch:
        with using_scope(context_scope):
            result = (
                result_ref.download_result(version)
                if explicit_scope is None
                else result_ref.download_result(version, scope=explicit_scope)
            )

    assert type(result) is type(fetched[0])
    _assert_fetch_called_with_scope(
        fetch, result_ref, result_type, version, expected_scope
    )


@pytest.mark.parametrize("result_type,program_type", DEFAULT_RESULT_CASES)
@pytest.mark.parametrize("explicit_scope", [None, ScopeFilterEnum.GLOBAL_ADMIN])
def test_execution_result_download_backend_info_propagates_scope(
    explicit_scope: ScopeFilterEnum | None,
    result_type: ResultType,
    program_type: ProgramType,
) -> None:
    result_ref = _execution_result_ref(result_type)
    fetched = _fetched_result(result_type, program_type)
    context_scope = ScopeFilterEnum.ORG_ADMIN
    expected_scope = explicit_scope or context_scope

    with mock.patch.object(
        _execute, _fetch_name(result_type), return_value=fetched
    ) as fetch:
        with using_scope(context_scope):
            backend_info = (
                result_ref.download_backend_info()
                if explicit_scope is None
                else result_ref.download_backend_info(scope=explicit_scope)
            )

    assert backend_info == fetched[1]
    _assert_fetch_called_with_scope(
        fetch,
        result_ref,
        result_type,
        ResultVersions.DEFAULT,
        expected_scope,
    )


@pytest.mark.parametrize("explicit_scope", [None, ScopeFilterEnum.GLOBAL_ADMIN])
def test_download_h2_qsysresult_propagates_scope(
    explicit_scope: ScopeFilterEnum | None,
) -> None:
    result_ref = _execution_result_ref()
    backend_result = BackendResult()
    qsys_result = mock.sentinel.qsys_result
    context_scope = ScopeFilterEnum.ORG_ADMIN
    expected_scope = explicit_scope or context_scope

    with (
        mock.patch.object(
            ExecutionResultRef, "download_result", return_value=backend_result
        ) as download_result,
        mock.patch(
            "hugr_qir.h_series_helpers.results.backendresult_to_qsysresult",
            return_value=qsys_result,
        ) as convert_result,
    ):
        with using_scope(context_scope):
            result = (
                result_ref.download_h2_qsysresult()
                if explicit_scope is None
                else result_ref.download_h2_qsysresult(scope=explicit_scope)
            )

    assert result is qsys_result
    download_result.assert_called_once_with(scope=expected_scope)
    convert_result.assert_called_once_with(backend_result)


def test_assignments_passes_scope_to_assignee_fetches() -> None:
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    role = _role()
    scope = ScopeFilterEnum.GLOBAL_ADMIN
    response = mock.MagicMock(status_code=200)
    response.json.return_value = {
        "data": {
            "attributes": {
                "user_role_assignments": [
                    {"user_id": user_id, "role_id": str(role.id)}
                ],
                "team_role_assignments": [
                    {"team_id": team_id, "role_id": str(role.id)}
                ],
                "public_role_assignments": [],
            }
        }
    }
    client = mock.MagicMock()
    client.get.return_value = response

    with (
        mock.patch.object(roles, "get_nexus_client", return_value=client),
        mock.patch.object(roles, "get_all", return_value=[role]),
        mock.patch.object(
            users,
            "_fetch_by_id",
            return_value=UserRef(id=user_id, display_name="Test User"),
        ) as fetch_user,
        mock.patch.object(
            teams,
            "_fetch_by_id",
            return_value=TeamRef(id=team_id, name="Test Team", description=None),
        ) as fetch_team,
    ):
        project = _project_ref()
        roles.assignments(project, scope=scope)

    fetch_user.assert_called_once_with(user_id=user_id, scope=scope)
    fetch_team.assert_called_once_with(team_id=team_id, scope=scope)
    client.get.assert_called_once_with(
        f"/api/resources/v1beta2/{project.id}/assignments",
        params={"scope": scope.value},
    )


def test_assign_user_passes_scope_to_assignment_request() -> None:
    scope = ScopeFilterEnum.GLOBAL_ADMIN
    user_id = uuid.uuid4()
    client = mock.MagicMock()
    user_response = mock.MagicMock(status_code=200)
    user_response.json.return_value = {"data": {"id": str(user_id)}}
    assignment_response = mock.MagicMock(status_code=201)
    client.get.return_value = user_response
    client.post.return_value = assignment_response
    project = _project_ref()
    role = _role()

    with mock.patch.object(roles, "get_nexus_client", return_value=client):
        roles.assign_user(
            project,
            user_email="test@example.com",
            role=role,
            scope=scope,
        )

    client.get.assert_called_once_with(
        "/api/users/v1beta/test@example.com", params={"scope": scope.value}
    )
    client.post.assert_called_once_with(
        "/api/assignments/v1beta2/user",
        json={
            "for_user_id": str(user_id),
            "role_id": str(role.id),
            "resource_id": str(project.id),
        },
        params={"scope": scope.value},
    )
