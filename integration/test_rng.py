"""Test RNG capabilities."""

from typing import Callable, ContextManager

import numpy as np
from pytket.backends.backendresult import BackendResult
from pytket.circuit import Bit, Circuit

import qnexus as qnx
from qnexus.models.references import (
    CircuitRef,
    ExecutionResultRef,
)


def get_rng_circuit(seed: int, n_rng: int, test_index: bool = False) -> Circuit:
    """Creates a single qubit pytket circuit to test RNGs.

    Note: see https://docs.quantinuum.com/systems/trainings/h2/getting_started/rng.html
          and https://docs.quantinuum.com/tket/api-docs/circuit_class.html#rng-operations
    """
    circuit = Circuit(1)

    rng_regs = []
    for i in range(n_rng):
        rng_regs.append(circuit.add_c_register(f"rng{i}", 32))

    seed_reg = circuit.add_c_register("seed", 64)
    circuit.add_c_setreg(seed, seed_reg)
    circuit.set_rng_seed(seed_reg)

    job_shot_reg = circuit.add_c_register("job_shot_num", 32)
    circuit.get_job_shot_num(job_shot_reg)

    if test_index:
        # set rng index = job_shotnum * num_rng_calls
        index_reg = circuit.add_c_register("index", 32)
        circuit.add_clexpr_from_logicexp(job_shot_reg * n_rng, index_reg.to_list())
        circuit.set_rng_index(index_reg)

    for rng_reg in rng_regs:
        circuit.get_rng_num(rng_reg)
    circuit.measure_all()

    return circuit


def ints_from_pytket_shots(shots: np.ndarray) -> list[int]:
    """Convert pytket register shots to integers.

    Args:
        shots: Array of shape (n_shots, n_bits) from result.get_shots(cbits=reg).
               Column i corresponds to reg[i], with reg[0] as the LSB.

    Returns:
        List of integers, one per shot.
    """
    powers = 1 << np.arange(shots.shape[1])
    return list(map(int, (shots @ powers).tolist()))


def test_rng(
    test_case_name: str,
    create_circuit_in_project: Callable[
        [Circuit, str, str], ContextManager[CircuitRef]
    ],
) -> None:
    """Test that we can run RNG circuits in H-Series machines."""
    local_project_name = f"project for {test_case_name}"
    backend_config = qnx.QuantinuumConfig(device_name="H2-1E")
    n_shots = 5
    n_rng = 3

    rng_circuit_case1 = get_rng_circuit(42, n_rng, test_index=False)
    rng_circuit_case2 = get_rng_circuit(42, n_rng, test_index=True)
    rng_circuit_case3 = get_rng_circuit(24, n_rng, test_index=False)

    # Pytket "rngX" registers to extract the RNG numbers from the results.
    rng_reg_names = []
    for rng in range(n_rng):
        rng_reg_names.append(f"rng{rng}")

    with create_circuit_in_project(
        rng_circuit_case1,
        local_project_name,
        f"RNG circuit 1 for {test_case_name}",
    ) as rng_circ_case1_ref:
        with create_circuit_in_project(
            rng_circuit_case2,
            local_project_name,
            f"RNG circuit 2 for {test_case_name}",
        ) as rng_circ_case2_ref:
            with create_circuit_in_project(
                rng_circuit_case3,
                local_project_name,
                f"RNG circuit 3 for {test_case_name}",
            ) as rng_circ_case3_ref:
                my_proj = qnx.projects.get(name=local_project_name)

                execute_job_case1 = qnx.start_execute_job(
                    programs=[rng_circ_case1_ref, rng_circ_case1_ref],
                    name=f"Same seed no index RNG job for {test_case_name}",
                    project=my_proj,
                    backend_config=backend_config,
                    n_shots=[n_shots, n_shots],
                )
                execute_job_case2 = qnx.start_execute_job(
                    programs=[rng_circ_case2_ref],
                    name=f"Same seed with index RNG job for {test_case_name}",
                    project=my_proj,
                    backend_config=backend_config,
                    n_shots=[n_shots],
                )
                execute_job_case3 = qnx.start_execute_job(
                    programs=[rng_circ_case3_ref],
                    name=f"Different seed no index RNG job for {test_case_name}",
                    project=my_proj,
                    backend_config=backend_config,
                    n_shots=[n_shots],
                )

                # Case 1: Executing a circuit with the same seed and no index
                #         multiple times should give the same RNG numbers in all shots.
                qnx.jobs.wait_for(execute_job_case1)
                results_same = qnx.jobs.results(execute_job_case1)
                rng1_A_result_ref = results_same[0]
                rng1_B_result_ref = results_same[1]
                assert isinstance(rng1_A_result_ref, ExecutionResultRef)
                assert isinstance(rng1_B_result_ref, ExecutionResultRef)

                rng1_A_result = rng1_A_result_ref.download_result()
                rng1_B_result = rng1_B_result_ref.download_result()
                assert isinstance(rng1_A_result, BackendResult)
                assert isinstance(rng1_B_result, BackendResult)

                for rng_reg_name in rng_reg_names:
                    reg = [Bit(f"{rng_reg_name}", i) for i in range(32)]

                    rng1_A_numbers = ints_from_pytket_shots(
                        rng1_A_result.get_shots(cbits=reg)
                    )
                    rng1_B_numbers = ints_from_pytket_shots(
                        rng1_B_result.get_shots(cbits=reg)
                    )

                    assert len(rng1_A_numbers) == len(rng1_B_numbers)
                    assert rng1_A_numbers == rng1_B_numbers, (
                        f"RNG numbers of {rng_reg_name} generated with the same seed should be equal."
                    )

                # Case 2: Executing the same circuit with the same seed and changing the
                #         index should give different RNG numbers in all shots.
                qnx.jobs.wait_for(execute_job_case2)
                results_index = qnx.jobs.results(execute_job_case2)
                rng2_result_ref = results_index[0]
                assert isinstance(rng2_result_ref, ExecutionResultRef)

                rng2_result = rng2_result_ref.download_result()
                assert isinstance(rng2_result, BackendResult)

                all_shots_numbers = []
                for rng_reg_name in rng_reg_names:
                    reg = [Bit(f"{rng_reg_name}", i) for i in range(32)]

                    all_shots_numbers.extend(
                        ints_from_pytket_shots(rng2_result.get_shots(cbits=reg))
                    )

                assert len(set(all_shots_numbers)) == len(all_shots_numbers), (
                    "All RNG numbers should be different across shots."
                )

                # Case 3: Executing the circuit with a different seed should give
                #         a different RNG number than the case 1 execution.
                qnx.jobs.wait_for(execute_job_case3)
                results_diff = qnx.jobs.results(execute_job_case3)
                rng3_result_ref = results_diff[0]
                assert isinstance(rng3_result_ref, ExecutionResultRef)

                rng3_result = rng3_result_ref.download_result()
                assert isinstance(rng3_result, BackendResult)

                for rng_reg_name in rng_reg_names:
                    reg = [Bit(f"{rng_reg_name}", i) for i in range(32)]

                    rng3_numbers = ints_from_pytket_shots(
                        rng3_result.get_shots(cbits=reg)
                    )

                    assert rng1_A_numbers != rng3_numbers, (
                        f"RNG numbers of {rng_reg_name} generated with a different seed should be different."
                    )
