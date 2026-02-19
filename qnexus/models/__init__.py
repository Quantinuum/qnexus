"""Models for use by the client."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from logging import getLogger
from typing import Literal, Optional, Union
from uuid import UUID

import pandas as pd
from pydantic import BaseModel, ConfigDict, field_validator
from pytket.architecture import Architecture, FullyConnected
from pytket.backends.backendinfo import BackendInfo
from pytket.circuit import Node, OpType
from quantinuum_schemas.models.backend_config import (
    AerConfig,
    AerStateConfig,
    AerUnitaryConfig,
    BackendConfig,
    BraketConfig,
    HeliosConfig,
    HeliosEmulatorConfig,
    IBMQConfig,
    IBMQEmulatorConfig,
    QuantinuumConfig,
    QulacsConfig,
    SeleneConfig,
    SelenePlusConfig,
)
from quantinuum_schemas.models.backend_info import Register, StoredBackendInfo
from quantinuum_schemas.models.emulator_config import (
    ClassicalReplaySimulator,
    CoinflipSimulator,
    DepolarizingErrorModel,
    HeliosCustomErrorModel,
    HeliosRuntime,
    MatrixProductStateSimulator,
    NoErrorModel,
    QSystemErrorModel,
    SimpleRuntime,
    StabilizerSimulator,
    StatevectorSimulator,
)
from quantinuum_schemas.models.quantinuum_systems_noise import (
    HeliosErrorParams,
    UserErrorParams,
)

from qnexus.models.annotations import Annotations
from qnexus.models.job_status import WAITING_STATUS, JobStatusEnum
from qnexus.models.references import TeamRef, UserRef
from qnexus.models.utils import assert_never

logger = getLogger(__name__)

__all__ = [
    "AerConfig",
    "AerStateConfig",
    "AerUnitaryConfig",
    "BackendConfig",
    "SeleneConfig",
    "BraketConfig",
    "ClassicalReplaySimulator",
    "CoinflipSimulator",
    "IBMQConfig",
    "IBMQEmulatorConfig",
    "MatrixProductStateSimulator",
    "QuantinuumConfig",
    "QulacsConfig",
    "SelenePlusConfig",
    "StabilizerSimulator",
    "StatevectorSimulator",
    "StoredBackendInfo",
    "SimpleRuntime",
    "NoErrorModel",
    "DepolarizingErrorModel",
    "JobStatusEnum",
    "WAITING_STATUS",
    "QSystemErrorModel",
    "UserErrorParams",
    "HeliosConfig",
    "HeliosRuntime",
    "HeliosEmulatorConfig",
    "HeliosCustomErrorModel",
    "HeliosErrorParams",
]


class CredentialIssuer(str, Enum):
    """An Issuer of credentials."""

    QUANTINUUM = "Quantinuum"
    QISKIT = "Qiskit"
    BRAKET = "Braket"


class Credential(BaseModel):
    """A saved credential for a backend provider/issuer."""

    name: str
    backend_issuer: CredentialIssuer
    is_default_for_issuer: bool
    submitted_time: datetime
    id: str

    def df(self) -> pd.DataFrame:
        """Convert to a pandas DataFrame."""
        return pd.DataFrame(
            {
                "name": self.name,
                "issuer": self.backend_issuer,
                "is_default_for_issuer": self.is_default_for_issuer,
                "created": self.submitted_time,
                "id": self.id,
            },
            index=[0],
        )


class Device(BaseModel):
    """A device in Nexus."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    backend_name: str
    device_name: Optional[str]
    nexus_hosted: bool
    stored_backend_info: StoredBackendInfo

    @property
    def backend_info(self) -> BackendInfo:
        """The BackendInfo for the Device."""
        return to_pytket_backend_info(self.stored_backend_info)

    def df(self) -> pd.DataFrame:
        """Present in a pandas DataFrame."""
        return pd.DataFrame(
            {
                "backend_name": self.backend_name,
                "device_name": self.device_name,
                "nexus_hosted": self.nexus_hosted,
                "backend_info": to_pytket_backend_info(self.stored_backend_info),
            },
            index=[0],
        )

    @field_validator("backend_name")
    @classmethod
    def convert_backend_name(cls, v: str) -> str:
        """Convert the internal name for QuantinuumBackend."""
        if v == "EmulatorEnabledQuantinuumBackend":
            return "QuantinuumBackend"
        return v


class Quota(BaseModel):
    """A quota in Nexus."""

    name: str
    description: str
    usage: float
    quota: float | str

    def df(self) -> pd.DataFrame:
        """Convert to a pandas DataFrame."""
        return pd.DataFrame(self.model_dump(), index=[0])


class Role(BaseModel):
    """A role for use in RBAC assignments."""

    id: UUID
    name: str
    description: str
    permissions: str
    type: Literal["role"] = "role"

    def df(self) -> pd.DataFrame:
        """Convert to a pandas DataFrame."""
        return pd.DataFrame(
            {
                "name": self.name,
                "description": self.description,
                "permissions": self.permissions,
                "id": self.id,
            },
            index=[0],
        )


class RoleInfo(BaseModel):
    """Information on a role assigned on a resource."""

    assignment_type: Literal["user", "team", "public"]
    assignee: TeamRef | UserRef | None
    role: Role

    def df(self) -> pd.DataFrame:
        """Convert to a pandas DataFrame."""

        assignee_name: str | None = None
        match self.assignee:
            case TeamRef():
                assignee_name = self.assignee.name
            case UserRef():
                assignee_name = self.assignee.display_name
            case None:
                assignee_name = None
            case _:
                assert_never(self.assignee)

        return pd.DataFrame(
            {
                "assignment_type": self.assignment_type,
                "assignee": assignee_name,
                "role": self.role.name,
            },
            index=[0],
        )


class Property(BaseModel):
    """A property definition."""

    annotations: Annotations
    property_type: str
    required: bool
    color: str
    id: UUID

    def df(self) -> pd.DataFrame:
        """Convert to a pandas DataFrame."""
        return self.annotations.df().join(
            pd.DataFrame(
                {
                    "property_type": self.property_type,
                    "required": self.required,
                    "color": self.color,
                },
                index=[0],
            )
        )


class IssuerEnum(str, Enum):
    """Backend issuers in Nexus."""

    QUANTINUUM = "QUANTINUUM"
    IBMQ = "IBMQ"
    QISKIT = "QISKIT"
    BRAKET = "BRAKET"
    QULACS = "QULACS"


def issuer_enum_to_config_str(issuer: IssuerEnum) -> list[str]:
    """Convert an IssuerEnum to a list of BackendConfig names."""

    match issuer:
        case IssuerEnum.QUANTINUUM:
            return ["QuantinuumConfig"]
        case IssuerEnum.IBMQ:
            return ["IBMQConfig"]
        case IssuerEnum.QISKIT:
            return [
                "IBMQEmulatorConfig",
                "AerConfig",
                "AerStateConfig",
                "AerUnitaryConfig",
            ]
        case IssuerEnum.QULACS:
            return ["QulacsConfig"]
        case IssuerEnum.BRAKET:
            return ["BraketConfig"]
        case _:
            assert_never(issuer)


def _register_to_pytket_node(register: Register) -> Node:
    """Convert a pytket Node object from a nexus-dataclasses Register object."""

    return Node.from_list(list(register))


def to_pytket_backend_info(backend: StoredBackendInfo) -> BackendInfo:
    """Reconstruct a pytket BackendInfo from the StoredBackendInfo instance."""

    stored_nodes = backend.device.nodes
    stored_edges = backend.device.edges
    architecture_edge_list = []

    # BackendInfo dictionary attributes are initialised as None,
    # Then dictionaries are built when they are to be populated.
    # This is to satisfy type-checking as well as BackendInfo expectations/tests.

    averaged_node_gate_errors = None
    averaged_readout_errors = None
    all_node_gate_errors = None
    all_readout_errors = None

    for stored_node in stored_nodes:
        # Create node from register
        new_pytket_node = _register_to_pytket_node(stored_node.unitid)

        # Build average node gate errors
        if stored_node.average_error is not None:
            if averaged_node_gate_errors is None:
                averaged_node_gate_errors = {}
            averaged_node_gate_errors[new_pytket_node] = stored_node.average_error
        # Build average readout errors
        if stored_node.readout_error is not None:
            if averaged_readout_errors is None:
                averaged_readout_errors = {}
            averaged_readout_errors[new_pytket_node] = stored_node.readout_error

        if stored_node.gate_errors:
            node_gate_errors = {
                getattr(OpType, optype_name): error
                for optype_name, error in stored_node.gate_errors.items()
            }
            if all_node_gate_errors is None:
                all_node_gate_errors = {}
            all_node_gate_errors[new_pytket_node] = node_gate_errors

        # Add stored_node readout errors to all_readout_errors
        stored_zero_state_readout_error = stored_node.zero_state_readout_error
        stored_one_state_readout_error = stored_node.one_state_readout_error
        if (
            stored_zero_state_readout_error is not None
            and stored_one_state_readout_error is not None
        ):
            if all_readout_errors is None:
                all_readout_errors = {}
            readout_errors = [
                [
                    1.0 - stored_zero_state_readout_error,
                    stored_zero_state_readout_error,
                ],
                [
                    stored_one_state_readout_error,
                    1.0 - stored_one_state_readout_error,
                ],
            ]
            all_readout_errors[new_pytket_node] = readout_errors

    # Build all_edge_gate_errors and averaged_edge_gate_errors from stored_edges
    all_edge_gate_errors = None
    averaged_edge_gate_errors = None

    for stored_edge in stored_edges:
        node_from = _register_to_pytket_node(stored_edge.unitid_from)
        node_to = _register_to_pytket_node(stored_edge.unitid_to)

        new_edge_tuple = (node_from, node_to)
        architecture_edge_list.append(new_edge_tuple)

        if stored_edge.average_error is not None:
            if averaged_edge_gate_errors is None:
                averaged_edge_gate_errors = {}
            averaged_edge_gate_errors[(node_from, node_to)] = stored_edge.average_error
        if stored_edge.gate_errors:
            edge_gate_errors = {
                getattr(OpType, optype_name): error
                for optype_name, error in stored_edge.gate_errors.items()
            }
            if all_edge_gate_errors is None:
                all_edge_gate_errors = {}
            all_edge_gate_errors[(node_from, node_to)] = edge_gate_errors

    architecture: Union[Architecture, FullyConnected] = (
        FullyConnected(
            backend.device.n_nodes
            if backend.device.n_nodes is not None
            else len(backend.device.nodes)
        )
        if backend.device.fully_connected
        else Architecture(architecture_edge_list)
    )

    gate_set = set()

    for gate in backend.gate_set:
        try:
            gate_set.add(getattr(OpType, gate))
        except AttributeError:
            logger.warning(
                "Unknown OpType in BackendInfo: `%`, will omit from BackendInfo."
                " Consider updating your pytket version.",
                gate,
            )

    return BackendInfo(
        name=backend.name,
        device_name=backend.device_name,
        version=backend.version,
        architecture=architecture,
        gate_set=gate_set,
        n_cl_reg=backend.n_cl_reg,
        supports_fast_feedforward=backend.supports_fast_feedforward,
        supports_reset=backend.supports_reset,
        supports_midcircuit_measurement=backend.supports_midcircuit_measurement,
        all_node_gate_errors=all_node_gate_errors,
        all_edge_gate_errors=all_edge_gate_errors,
        all_readout_errors=all_readout_errors,
        averaged_node_gate_errors=averaged_node_gate_errors,
        averaged_edge_gate_errors=averaged_edge_gate_errors,
        averaged_readout_errors=averaged_readout_errors,
        misc=backend.misc,
    )
