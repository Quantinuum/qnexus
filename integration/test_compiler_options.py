"""Test submitting compiler options for compilation jobs."""

from typing import Callable, ContextManager

import pytest
from pytket.circuit import Circuit, OpType

import qnexus as qnx
from qnexus.models.references import (
    CompilationResultRef,
    CompileJobRef,
)


def assert_op_count_in_circuit(
    circuit: Circuit, op: OpType, should_be_gt_0: bool
) -> None:
    """Assert that the number of `op` gates in the `circuit` is 0 or >0."""
    total_ops = sum([1 for circ_op in circuit.get_commands() if circ_op.op.type == op])
    if should_be_gt_0:
        assert total_ops > 0, (
            f"Expected >0 {op} gates in the circuit, but found {total_ops}."
        )
    else:
        assert total_ops == 0, (
            f"Expected 0 {op} gates in the circuit, but found {total_ops}."
        )


@pytest.mark.parametrize(
    "target_2qb_gate, expect_tk2_gt_0, expect_zzphase_gt_0, expect_zzmax_gt_0",
    [
        ("TK2", True, False, False),
        ("ZZPhase", False, True, False),
        ("ZZMax", False, False, True),
    ],
    ids=["TK2", "ZZPhase", "ZZMax"],
)
def test_target_2qb_gate(
    create_compile_job_in_project: Callable[..., ContextManager[CompileJobRef]],
    test_suite_name: str,
    test_case_name: str,
    test_qv_circuit: Circuit,
    target_2qb_gate: str,
    expect_tk2_gt_0: bool,
    expect_zzphase_gt_0: bool,
    expect_zzmax_gt_0: bool,
) -> None:
    """Test that we can submit compile jobs with different `target_2qb_gate`."""

    project_name = f"project for {test_suite_name}"
    circuit_name = f"circuit foro {test_case_name}"
    compile_job_name = f"compile job for {test_case_name}"

    device_name = "H2-Emulator"
    config = qnx.QuantinuumConfig(
        device_name=device_name,
        compiler_options={"target_2qb_gate": target_2qb_gate},
    )

    with create_compile_job_in_project(
        project_name=project_name,
        job_name=compile_job_name,
        circuit=test_qv_circuit,
        circuit_name=circuit_name,
        backend_config=config,
        skip_intermediate_circuits=True,
    ) as compile_job_ref:
        qnx.jobs.wait_for(compile_job_ref)
        compile_result = qnx.jobs.results(compile_job_ref)[0]
        assert isinstance(compile_result, CompilationResultRef)
        compiled_circuit_ref = compile_result.get_output()
        compiled_circuit = compiled_circuit_ref.download_circuit()

        assert_op_count_in_circuit(compiled_circuit, OpType.TK2, expect_tk2_gt_0)
        assert_op_count_in_circuit(
            compiled_circuit, OpType.ZZPhase, expect_zzphase_gt_0
        )
        assert_op_count_in_circuit(compiled_circuit, OpType.ZZMax, expect_zzmax_gt_0)
