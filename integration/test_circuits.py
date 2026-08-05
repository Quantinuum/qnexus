"""Test basic functionality relating to the circuit module."""

from typing import Callable, ContextManager

import pandas as pd
import pytest
from pytket.circuit import Circuit

from constants import JOB_TIMEOUT
import qnexus as qnx
import qnexus.exceptions as qnx_exc
from qnexus.models.annotations import PropertiesDict
from qnexus.models.references import CircuitRef, ProjectRef, Ref

test_circuit = Circuit(2, 2).H(0).CX(0, 1).measure_all()


def test_circuit_get(
    test_case_name: str,
    create_circuit_in_project: Callable[
        [Circuit, str, str], ContextManager[CircuitRef]
    ],
    test_ref_serialisation: Callable[[str, Ref], None],
) -> None:
    """Test that we can create a circuit, add a property value,
    get a specific unique CircuitRef by name or id,  get an iterator over all circuits,
    and the serialisation round trip of a CircuitRef.
    """

    with create_circuit_in_project(
        test_circuit,
        f"project for {test_case_name}",
        f"circuit for {test_case_name}",
    ) as my_circ_ref:
        assert isinstance(my_circ_ref, CircuitRef)
        assert isinstance(my_circ_ref.download_circuit(), Circuit)

        my_circ_2 = qnx.circuits.get(id=my_circ_ref.id)

        # For some reason direct equality check fails
        assert my_circ_ref.id == my_circ_2.id
        assert my_circ_ref.annotations == my_circ_2.annotations
        assert my_circ_ref.project.id == my_circ_2.project.id

        with pytest.raises(qnx_exc.NoUniqueMatch):
            qnx.circuits.get()

        with pytest.raises(qnx_exc.ZeroMatches):
            qnx.circuits.get(name=f"{test_case_name}-wrong")

        test_ref_serialisation("circuit", my_circ_2)


def test_circuit_get_all(
    test_case_name: str,
    create_circuit_in_project: Callable[
        [Circuit, str, str], ContextManager[CircuitRef]
    ],
) -> None:
    """Test that we can get an iterator over all circuits."""

    project_name = f"project for {test_case_name}"

    with create_circuit_in_project(
        test_circuit,
        project_name,
        f"circuit1 for {test_case_name}",
    ):
        with create_circuit_in_project(
            test_circuit,
            project_name,
            f"circuit2 for {test_case_name}",
        ):
            my_circ_db_matches = qnx.circuits.get_all(name_like=test_case_name)

            assert my_circ_db_matches.count() == 2
            assert isinstance(my_circ_db_matches.summarize(), pd.DataFrame)
            assert isinstance(next(my_circ_db_matches), CircuitRef)


def test_circuit_create(
    test_case_name: str,
    create_property_in_project: Callable[..., ContextManager[ProjectRef]],
) -> None:
    """Test that we can create a circuit and add a property value."""

    project_name = f"project for {test_case_name}"
    property_name = f"property for {test_case_name}"

    with create_property_in_project(
        project_name=project_name,
        property_name=property_name,
        property_type="string",
        required=False,
    ):
        my_proj = qnx.projects.get(name=project_name)

        circuit_name = f"circuit for {test_case_name}"
        my_circ = Circuit(2, 2).H(0).CX(0, 1).measure_all()
        my_new_circuit = qnx.circuits.upload(
            circuit=my_circ, name=circuit_name, project=my_proj
        )

        assert isinstance(my_new_circuit, CircuitRef)

        test_prop_value = "foo"

        updated_circuit_ref = qnx.circuits.update(
            ref=my_new_circuit,
            properties=PropertiesDict({property_name: test_prop_value}),
        )

        assert (
            updated_circuit_ref.annotations.properties[property_name] == test_prop_value
        )


@pytest.mark.parametrize(
    "device_name, syntax_checker, expected_exception",
    [
        ["H2-1", "H2-1SC", False],
        ["H2-1", None, False],
        ["H2-1SC", None, False],
        ["H1-1", "H1-1SC", True],
        ["H1-1", None, True],
        ["Foo", "Bar", True],
    ],
)
def test_circuit_get_cost(
    test_case_name: str,
    create_project: Callable[[str], ContextManager[ProjectRef]],
    device_name: str,
    syntax_checker: str | None,
    expected_exception: bool,
) -> None:
    """Test that we can get the cost to run a CircuitRef,
    on a particular Quantinuum Systems device."""

    with create_project(f"project for {test_case_name}") as my_proj:
        my_q_systems_circuit = qnx.circuits.upload(
            circuit=Circuit(2, 2).ZZPhase(0.5, 0, 1).measure_all(),
            name="qa_q_systems_circuit",
            project=my_proj,
        )
        if expected_exception:
            with pytest.raises(ValueError):
                qnx.circuits.cost(
                    circuit_ref=my_q_systems_circuit,
                    n_shots=10,
                    backend_config=qnx.QuantinuumConfig(device_name=device_name),
                    syntax_checker=syntax_checker,
                    project=my_proj,
                )
        else:
            cost = qnx.circuits.cost(
                circuit_ref=my_q_systems_circuit,
                n_shots=10,
                backend_config=qnx.QuantinuumConfig(device_name=device_name),
                syntax_checker=syntax_checker,
                project=my_proj,
                timeout=JOB_TIMEOUT,
            )

            assert isinstance(cost, float)
            assert cost > 0.0
