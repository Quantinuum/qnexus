"""Test basic functionality relating to the wasm_modules module."""

from typing import Callable, ContextManager

import pandas as pd
from pytket.circuit import Circuit
from pytket.wasm.wasm import WasmFileHandler, WasmModuleHandler

import qnexus as qnx
from qnexus.models.job_status import JobStatusEnum
from qnexus.models.references import Ref, WasmModuleRef

from constants import JOB_TIMEOUT


def test_wasm_download(
    test_case_name: str,
    create_wasm_in_project: Callable[
        [str, str, WasmModuleHandler], ContextManager[WasmModuleRef]
    ],
    qa_wasm_module: WasmFileHandler,
    test_ref_serialisation: Callable[[str, Ref], None],
) -> None:
    """Test that valid WASM can be extracted from an uploaded WASM module,
    and the WasmModuleRef serialisation round trip."""

    project_name = f"project for {test_case_name}"
    wasm_module_name = f"wasm for {test_case_name}"

    with create_wasm_in_project(
        project_name,
        wasm_module_name,
        qa_wasm_module,
    ) as wasm_ref:
        assert isinstance(wasm_ref, WasmModuleRef)
        downloaded_wasm_module_handler = wasm_ref.download_wasm_contents()

        downloaded_wasm_module_handler.check()
        assert downloaded_wasm_module_handler.functions == qa_wasm_module.functions

        wasm_ref_by_id = qnx.wasm_modules.get(id=wasm_ref.id)
        test_ref_serialisation("wasm", wasm_ref_by_id)


def test_wasm_flow(
    test_case_name: str,
    create_wasm_in_project: Callable[
        [str, str, WasmModuleHandler], ContextManager[WasmModuleRef]
    ],
    qa_wasm_module: WasmFileHandler,
) -> None:
    """Test the flow for executing a simple WASM circuit on H1-1LE."""

    project_name = f"project for {test_case_name}"
    wasm_module_name = f"wasm for {test_case_name}"

    with create_wasm_in_project(
        project_name,
        wasm_module_name,
        qa_wasm_module,
    ) as wasm_ref:
        proj_ref = qnx.projects.get(name=project_name)

        my_wasm_db_matches = qnx.wasm_modules.get_all()
        assert isinstance(my_wasm_db_matches.summarize(), pd.DataFrame)
        assert isinstance(next(my_wasm_db_matches), WasmModuleRef)

        wasm_ref = qnx.wasm_modules.get(name=wasm_module_name)
        assert isinstance(wasm_ref, WasmModuleRef)

        wasm_ref_2 = qnx.wasm_modules.get(id=wasm_ref.id)
        assert wasm_ref == wasm_ref_2

        circuit = Circuit(1)
        a = circuit.add_c_register("a", 8)
        circuit.add_wasm_to_reg("add_one", qa_wasm_module, [a], [a])
        circuit.measure_all()
        qa_wasm_circuit_name_fixture = f"circuit with wasm for {test_case_name}"

        wasm_circuit_ref = qnx.circuits.upload(
            name=qa_wasm_circuit_name_fixture,
            circuit=circuit,
            project=proj_ref,
        )

        execute_job_ref = qnx.start_execute_job(
            programs=[wasm_circuit_ref],
            name=f"wasm execute job for {test_case_name}",
            n_shots=[100],
            backend_config=qnx.QuantinuumConfig(
                device_name="H1-Emulator",
            ),
            wasm_module=wasm_ref,
            project=proj_ref,
        )

        qnx.jobs.wait_for(execute_job_ref, timeout=JOB_TIMEOUT)
        assert qnx.jobs.status(execute_job_ref).status == JobStatusEnum.COMPLETED
