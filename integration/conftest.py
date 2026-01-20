"""Pytest fixtures and settings used in the qnexus integration tests."""

import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, ContextManager, Generator, Literal, Union, cast

import pandas as pd
import pytest
from hugr.package import Package
from pytket.circuit import Circuit
from pytket.qir import pytket_to_qir  # type: ignore[attr-defined]
from pytket.wasm.wasm import WasmFileHandler, WasmModuleHandler
from quantinuum_schemas.models.backend_config import (
    AerConfig,
    AerStateConfig,
    AerUnitaryConfig,
    BackendConfig,
    BraketConfig,
    IBMQConfig,
    IBMQEmulatorConfig,
    QuantinuumConfig,
    QulacsConfig,
    SeleneConfig,
    SelenePlusConfig,
)

import qnexus as qnx
from qnexus.client.auth import login_no_interaction
from qnexus.config import CONFIG
from qnexus.exceptions import (
    NoUniqueMatch,
    ResourceDeleteFailed,
    ResourceUpdateFailed,
    ZeroMatches,
)
from qnexus.filesystem import load, save
from qnexus.models.references import (
    CircuitRef,
    CompileJobRef,
    ExecuteJobRef,
    GpuDecoderConfigRef,
    HUGRRef,
    ProjectRef,
    QIRRef,
    Ref,
    TeamRef,
    WasmModuleRef,
)

test_run_identifier = ""

AllBackendConfigs = Union[
    AerConfig,
    AerStateConfig,
    AerUnitaryConfig,
    BackendConfig,
    SeleneConfig,
    BraketConfig,
    IBMQConfig,
    IBMQEmulatorConfig,
    QuantinuumConfig,
    QulacsConfig,
    SelenePlusConfig,
]


LOGGER = logging.getLogger(__name__)


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--purge-projects",
        action="store_true",
        default=False,
        help="Purge the projects created by the tests.",
    )

    parser.addoption(
        "--run-id",
        action="store",
        default="",
        help="Use this to identify resources created by the tests. If not provided the `testrun_uid` from pytest-xdist is used.",
    )


@pytest.fixture(autouse=True)
def set_test_run_identifier(request: pytest.FixtureRequest, testrun_uid: str) -> None:
    global test_run_identifier

    run_id_option = request.config.getoption("--run-id")
    test_run_identifier = run_id_option if run_id_option else testrun_uid


@pytest.fixture(name="test_case_name")
def fixture_test_case_name(request: pytest.FixtureRequest) -> str:
    test_case_name = f"{request.node.module.__name__}::{request.node.name}"
    return f"qnexus.{test_case_name}, run:{request.node.execution_count}, id:{test_run_identifier}"


@pytest.fixture(name="test_suite_name")
def fixture_test_suite_name(request: pytest.FixtureRequest) -> str:
    test_suite_name = f"{request.node.module.__name__}"
    return f"qnexus.{test_suite_name}, run:{request.node.execution_count}, id:{test_run_identifier}"


@pytest.fixture(scope="session", autouse=True)
def authenticated_nexus(
    user_email: str = CONFIG.qa_user_email,
    user_password: str = CONFIG.qa_user_password,
) -> Generator[None, None, None]:
    """Authenticated nexus instance fixture."""
    try:
        login_no_interaction(user_email, user_password)
        yield
    finally:
        qnx.auth.logout()


@pytest.fixture(name="create_team")
def fixture_create_team() -> Callable[[str], ContextManager[TeamRef]]:
    """Returns a `ContextManager` that yields a `TeamRef`
    of an existing/created project with the specified name."""

    @contextmanager
    def make_team_if_needed(
        team_name: str,
    ) -> Generator[TeamRef, None, None]:
        team_ref = None
        try:
            team_ref = qnx.teams.get(team_name)
        except ZeroMatches:
            team_ref = qnx.teams.create(
                name=team_name, description=f"description for {team_name}"
            )
        except Exception as e:
            raise e

        yield team_ref

    return make_team_if_needed


@pytest.fixture(name="create_project")
def fixture_create_project(
    request: pytest.FixtureRequest,
) -> Callable[[str], ContextManager[ProjectRef]]:
    """Returns a `ContextManager` that yields a `ProjectRef` of the
    project created with the specified name."""

    @contextmanager
    def make_temp_project(
        project_name: str,
    ) -> Generator[ProjectRef, None, None]:
        my_proj = qnx.projects.get_or_create(
            name=project_name, description=f"description for {project_name}"
        )
        yield my_proj

        if request.config.getoption("--purge-projects"):
            # If fixtures that use the `create_project`fixture are chained or
            # composed, multiple calls to archive and delete the same project
            # will be executed. In case that happens, we are just logging
            # a warning here.
            try:
                qnx.projects.update(my_proj, archive=True)
                qnx.projects.delete(my_proj)
            except ResourceUpdateFailed:
                LOGGER.warning(f"Project {project_name} is already archived")
            except ResourceDeleteFailed:
                LOGGER.warning(f"Project {project_name} is already deleted")
            except Exception as e:
                raise e

    return make_temp_project


@pytest.fixture(name="create_circuit_in_project")
def fixture_create_circuit_in_project(
    authenticated_nexus: None,
) -> Callable[[Circuit, str, str], ContextManager[CircuitRef]]:
    """Returns a `ContextManager` that yields a `CircuitRef` of the
    specified `circuit` uploaded to a project with `project_name`."""

    @contextmanager
    def upload_circuit_if_needed(
        circuit: Circuit,
        project_name: str,
        circuit_name: str,
    ) -> Generator[CircuitRef, None, None]:
        circuit_ref = _get_or_create_circuit(
            circuit=circuit, project_name=project_name, circuit_name=circuit_name
        )

        yield circuit_ref

    return upload_circuit_if_needed


@pytest.fixture(name="create_compile_job_in_project")
def fixture_create_compile_job_in_project(
    create_circuit_in_project: Callable[
        [Circuit, str, str], ContextManager[CircuitRef]
    ],
) -> Callable[..., ContextManager[CompileJobRef]]:
    """Returns a `ContextManager` that yields a `CompileJobRef` of the
    compile job submitted with the specified `CircuitRef` to the project
    with the provided name.

    Notes:
        - The default backend_config is `qnx.AerConfig()`
        - By default `skip_intermediate_circuits` is False

    Warning:
        - Will create the project and upload the circuit if needed.
        - Will not wait for the job to finish before yielding."""

    @contextmanager
    def make_compile_job(
        project_name: str,
        job_name: str,
        circuit: Circuit,
        circuit_name: str,
        backend_config: AllBackendConfigs | None = None,
        skip_intermediate_circuits: bool = False,
    ) -> Generator[CompileJobRef, None, None]:
        with create_circuit_in_project(
            circuit,
            project_name,
            circuit_name,
        ) as circuit_ref:
            config = backend_config if backend_config is not None else qnx.AerConfig()

            try:
                compile_job_ref = qnx.jobs.get(name=job_name)
            except ZeroMatches:
                proj_ref = qnx.projects.get(name=project_name)

                compile_job_ref = qnx.start_compile_job(
                    programs=[circuit_ref],
                    name=job_name,
                    description=f"description for {job_name}",
                    project=proj_ref,
                    backend_config=config,
                    skip_intermediate_circuits=skip_intermediate_circuits,
                )

            except Exception as e:
                raise e

            assert isinstance(compile_job_ref, CompileJobRef)
            yield compile_job_ref

    return make_compile_job


@pytest.fixture(name="create_execute_job_in_project")
def fixture_create_execute_job_in_project(
    create_circuit_in_project: Callable[
        [Circuit, str, str], ContextManager[CircuitRef]
    ],
) -> Callable[..., ContextManager[ExecuteJobRef]]:
    """Returns a `ContextManager` that yields a `ExecuteJobRef` of the
    execute job submitted with the specified `CircuitRef` to the project
    with the provided name.

    Notes:
        - A single element/circuit job is created.
        - The default backend_config is `qnx.AerConfig()`.
        - By default 10 shots are executed.

    Warning:
        - Will create the project and upload the circuit if needed.
        - Will not wait for the job to finish before yielding."""

    @contextmanager
    def make_execute_job(
        project_name: str,
        job_name: str,
        circuit: Circuit,
        circuit_name: str,
        backend_config: AllBackendConfigs | None = None,
        n_shots: int = 10,
    ) -> Generator[ExecuteJobRef, None, None]:
        with create_circuit_in_project(
            circuit,
            project_name,
            circuit_name,
        ) as circuit_ref:
            config = backend_config if backend_config is not None else qnx.AerConfig()

            try:
                execute_job_ref = qnx.jobs.get(name=job_name)
            except (ZeroMatches, NoUniqueMatch):
                proj_ref = qnx.projects.get(name=project_name)

                execute_job_ref = qnx.start_execute_job(
                    programs=[circuit_ref],
                    name=job_name,
                    description=f"description for {job_name}",
                    project=proj_ref,
                    backend_config=config,
                    n_shots=[n_shots],
                )

            assert isinstance(execute_job_ref, ExecuteJobRef)
            yield execute_job_ref

    return make_execute_job


@pytest.fixture(name="create_property_in_project")
def fixture_create_property_in_project(
    create_project: Callable[[str], ContextManager[ProjectRef]],
) -> Callable[..., ContextManager[ProjectRef]]:
    """Returns a `ContextManager` that yields a `ProjectRef` to the project with
    `project_name` where the specified property was created.

    Notes: will create the project if it does not exist."""

    @contextmanager
    def make_temp_property(
        project_name: str,
        property_name: str,
        property_type: Literal["bool", "int", "float", "string"],
        required: bool = False,
    ) -> Generator[ProjectRef, None, None]:
        with create_project(project_name) as proj_ref:
            qnx.projects.add_property(
                name=property_name,
                property_type=property_type,
                project=proj_ref,
                required=required,
            )

            yield proj_ref

    return make_temp_property


@pytest.fixture(name="create_qir_in_project")
def fixture_create_qir_in_project(
    create_project: Callable[[str], ContextManager[ProjectRef]],
) -> Callable[[str, str, bytes], ContextManager[QIRRef]]:
    """Returns a `ContextManager` that yields a `QIRRef` to the `qir_bitcode`
    uploaded to a project with `project_name`.

    Notes: will create the project if it does not exist."""

    @contextmanager
    def upload_qir(
        project_name: str,
        qir_name: str,
        qir: bytes,
    ) -> Generator[QIRRef, None, None]:
        with create_project(project_name) as proj_ref:
            qir_ref = qnx.qir.upload(qir=qir, name=qir_name, project=proj_ref)

            yield qir_ref

    return upload_qir


@pytest.fixture(name="create_hugr_in_project")
def fixture_create_hugr_in_project(
    create_project: Callable[[str], ContextManager[ProjectRef]],
) -> Callable[[str, str, Package], ContextManager[HUGRRef]]:
    """Returns a `ContextManager` that yields a `HUGRRef` to the `hugr_package`
    uploaded to a project with `project_name`.

    Notes: will create the project if it does not exist."""

    @contextmanager
    def upload_hugr(
        project_name: str,
        hugr_name: str,
        hugr_package: Package,
    ) -> Generator[HUGRRef, None, None]:
        with create_project(project_name) as proj_ref:
            hugr_ref = qnx.hugr.upload(
                hugr_package=hugr_package,
                name=hugr_name,
                project=proj_ref,
            )

            yield hugr_ref

    return upload_hugr


@pytest.fixture(name="create_wasm_in_project")
def fixture_create_wasm_in_project(
    create_project: Callable[[str], ContextManager[ProjectRef]],
) -> Callable[[str, str, WasmModuleHandler], ContextManager[WasmModuleRef]]:
    """Returns a `ContextManager` that yields a `WasmModuleRef` to the `wasm_module`
    uploaded to a project with `project_name`.

    Notes: will create the project if it does not exist."""

    @contextmanager
    def upload_wasm(
        project_name: str,
        wasm_module_name: str,
        wasm_module_handler: WasmModuleHandler,
    ) -> Generator[WasmModuleRef, None, None]:
        with create_project(project_name) as proj_ref:
            wasm_ref = qnx.wasm_modules.upload(
                wasm_module_handler=wasm_module_handler,
                name=wasm_module_name,
                project=proj_ref,
            )

            yield wasm_ref

    return upload_wasm


@pytest.fixture(name="create_gpu_decoder_config_in_project")
def fixture_create_gpu_decoder_config_in_project(
    create_project: Callable[[str], ContextManager[ProjectRef]],
) -> Callable[[str, str, str], ContextManager[GpuDecoderConfigRef]]:
    """Returns a `ContextManager` that yields a `GpuDecoderConfigRef` to the `gpu_decoder_config`
    uploaded to a project with `project_name`.

    Notes: will create the project if it does not exist."""

    @contextmanager
    def upload_gpu_decoder_config(
        project_name: str,
        gpu_decoder_config_name: str,
        gpu_decoder_config: str,
    ) -> Generator[GpuDecoderConfigRef, None, None]:
        with create_project(project_name) as proj_ref:
            gpu_decoder_config_ref = qnx.gpu_decoder_configs.upload(
                gpu_decoder_config=gpu_decoder_config,
                name=gpu_decoder_config_name,
                project=proj_ref,
            )

            yield gpu_decoder_config_ref

    return upload_gpu_decoder_config


@pytest.fixture(name="test_ref_serialisation")
def fixture_test_ref_serialisation(  # type: ignore[no-untyped-def]
    tmpdir,
) -> Callable[[str, Ref], None]:
    """Returns a function that tests the serialisation (save/load) of
    a reference."""

    def test_ref_serialisation(
        ref_type: str,
        ref: Ref,
    ) -> None:
        ref_path = tmpdir / ref_type
        save(ref=ref, path=ref_path)
        ref_loaded = load(path=ref_path)
        assert ref == ref_loaded

    return test_ref_serialisation


@pytest.fixture(name="qa_hugr_package")
def qa_hugr_package_fixture() -> Package:
    hugr_path = Path("tests/data/example_bell.hugr").resolve()
    return Package.from_bytes(hugr_path.read_bytes())


@pytest.fixture(name="qa_wasm_module")
def qa_wasm_module_fixture() -> WasmFileHandler:
    wasm_path = Path("examples/basics/data/add_one.wasm").resolve()
    return WasmFileHandler(filepath=str(wasm_path))


@pytest.fixture(name="qa_qir_bitcode")
def qa_qir_bitcode_fixture(test_circuit: Circuit, test_case_name: str) -> bytes:
    qir_bitcode = pytket_to_qir(test_circuit, name=f"qir for {test_case_name}")
    assert isinstance(qir_bitcode, bytes)
    return qir_bitcode


@pytest.fixture(name="qa_gpu_decoder_config")
def qa_gpu_decoder_config_fixture() -> str:
    gpu_decoder_config_path = Path(
        "examples/basics/data/gpu_decoder_config.yaml"
    ).resolve()
    with open(gpu_decoder_config_path) as fp:
        return fp.read()


def get_backend_config_name(backend_config: qnx.BackendConfig) -> str:
    name = backend_config.__class__.__name__

    if hasattr(backend_config, "backend_name"):
        name += f"({backend_config.backend_name})"
    if hasattr(backend_config, "device_name"):
        name += f"({backend_config.device_name})"
    return name


@pytest.fixture(
    scope="session",
    params=[
        # Nexus-hosted
        qnx.AerConfig(),
        qnx.AerStateConfig(),
        qnx.AerUnitaryConfig(),
        qnx.BraketConfig(local=True),
        qnx.QuantinuumConfig(device_name="H1-1LE"),
        qnx.QulacsConfig(),
        # Non Nexus-hosted
        qnx.IBMQConfig(
            backend_name="ibm_torino",
            instance=(
                "crn:v1:bluemix:public:quantum-computing:us-east:"
                "a/18f63f4565ef4a40851959792418cbf2:"
                "37bf946a-6349-47df-a092-3fbd5b92dbf2::"
            ),
        ),
        qnx.IBMQEmulatorConfig(
            backend_name="ibm_torino",
            instance=(
                "crn:v1:bluemix:public:quantum-computing:us-east:"
                "a/18f63f4565ef4a40851959792418cbf2:"
                "37bf946a-6349-47df-a092-3fbd5b92dbf2::"
            ),
        ),
        qnx.QuantinuumConfig(device_name="H1-1SC"),  # Cluster-hosted
    ],
    ids=get_backend_config_name,
)
def backend_config(request: pytest.FixtureRequest) -> BackendConfig:
    """Fixture to provide an instance of all BackendConfigs for testing."""
    return cast(BackendConfig, request.param)


@pytest.fixture()
def test_circuit() -> Circuit:
    """A pytket circuit to use in the integration tests."""

    circuit = Circuit(3)
    circuit.H(0)
    for i, j in zip(circuit.qubits[:-1], circuit.qubits[1:]):
        circuit.CX(i, j)
    circuit.measure_all()
    return circuit


def _get_or_create_circuit(
    circuit: Circuit,
    project_name: str,
    circuit_name: str,
) -> CircuitRef:
    """Get or create a circuit with `circuit_name` in a project with
    `project_name`."""

    project_ref = qnx.projects.get_or_create(project_name)

    # Using `qnx.circuits.get_all()` since the names of compiled
    # circuits are the same as the original circuits with some suffix,
    # which makes `qnx.circuits.get(namelike)` to return multiple circuits
    circuits_df = qnx.circuits.get_all(project=project_ref).df()

    circuits_filtered = pd.DataFrame()
    if len(circuits_df):
        circuits_filtered = circuits_df.loc[circuits_df["name"] == circuit_name]

    if len(circuits_filtered):
        circuit_ref = qnx.circuits.get(id=str(circuits_filtered.id.values[0]))
    else:
        circuit_ref = qnx.circuits.upload(
            circuit=circuit,
            name=circuit_name,
            description=f"description for {circuit_name}",
            project=project_ref,
        )

    return circuit_ref
