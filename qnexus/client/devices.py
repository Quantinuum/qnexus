"""Client API for devices in Nexus."""

from enum import Enum
from typing import Literal

from qnexus.client import get_nexus_client
from qnexus.exceptions import ResourceFetchFailed
from qnexus.models import (
    BackendConfig,
    Credential,
    Device,
    IssuerEnum,
    QuantinuumConfig,
    StoredBackendInfo,
    issuer_enum_to_config_str,
)
from qnexus.models.filters import DevicesFilter
from qnexus.models.references import DataframableList


class DeviceStateEnum(str, Enum):
    """Quantinuum Systems Device status enum."""

    ONLINE = "online"
    OFFLINE = "offline"
    MAINTENANCE = "in maintenance"
    RESERVED_ONLINE = "online, reserved"
    RESERVED_MAINTENANCE = "in maintenance, reserved"
    RESERVED_OFFLINE = "offline, reserved"


class Params(DevicesFilter):
    """Params for filtering devices."""


def get_all(
    issuers: list[IssuerEnum] | None = None,
    aws_region: str | None = None,
    ibm_instance: str | None = None,
    ibm_region: str | None = None,
    credentials: list[Credential] | None = None,
    credential_names: list[str] | None = None,
    nexus_hosted: bool | None = None,
) -> DataframableList[Device]:
    """Get all available devices."""

    issuer_config_names = (
        [
            config_str
            for issuer in issuers
            for config_str in issuer_enum_to_config_str(issuer)
        ]
        if issuers
        else []
    )

    params = Params(
        backend=issuer_config_names if issuer_config_names else None,
        region=aws_region,
        ibm_instance=ibm_instance,
        ibm_region=ibm_region,
        credential_ids=[cred.id for cred in credentials] if credentials else None,
        credential_names=credential_names,
        is_local=nexus_hosted,
    ).model_dump(by_alias=True, exclude_unset=True, exclude_none=True)

    res = get_nexus_client().get(
        "/api/v5/available_devices",
        params=params,
    )

    if res.status_code != 200:
        raise ResourceFetchFailed(message=res.text, status_code=res.status_code)

    device_list: DataframableList[Device] = DataframableList([])

    for backendinfolist in res.json():
        for backend_info in backendinfolist["backend_info_list"]:
            # Clean up the backend name for user consumption
            backend_name = backend_info["name"].replace("Backend", "")
            backend_name = backend_name.replace("EmulatorEnabled", "")

            device_list.append(
                Device(
                    backend_name=backend_name,
                    device_name=backend_info["device_name"],
                    nexus_hosted=backendinfolist["is_local"],
                    stored_backend_info=StoredBackendInfo(**backend_info),
                )
            )

    return device_list


def supports_shots(backend_config: BackendConfig) -> bool:
    """Does the backend configuration support shots?"""
    return _get_backend_property(backend_config, "supports_shots")


def supports_counts(backend_config: BackendConfig) -> bool:
    """Does the backend configuration support shots?"""
    return _get_backend_property(backend_config, "supports_counts")


def supports_state(backend_config: BackendConfig) -> bool:
    """Does the backend configuration support statevector results?"""
    return _get_backend_property(backend_config, "supports_state")


def supports_unitary(backend_config: BackendConfig) -> bool:
    """Does the backend configuration support a unitary?"""
    return _get_backend_property(backend_config, "supports_unitary")


def supports_density_matrix(backend_config: BackendConfig) -> bool:
    """Does the backend configuration support density matrix results?"""
    return _get_backend_property(backend_config, "supports_density_matrix")


def supports_expectation(backend_config: BackendConfig) -> bool:
    """Does the backend configuration support expectation values?"""
    return _get_backend_property(backend_config, "supports_expectation")


def expectation_allows_nonhermitian(backend_config: BackendConfig) -> bool:
    """Does the backend configuration support expectation_allows_nonhermitian?"""
    return _get_backend_property(backend_config, "expectation_allows_nonhermitian")


def supports_contextual_optimisation(backend_config: BackendConfig) -> bool:
    """Does the backend configuration support TKET contextual optimization?"""
    return _get_backend_property(backend_config, "supports_contextual_optimisation")


def status(backend_config: QuantinuumConfig) -> DeviceStateEnum:
    """Get the status of a hardware-hosted Quantinuum Systems device, such as
    whether is it online or offline.

    Please note this operation is not supported for cloud-hosted emulators,
    which can be assumed to be always online.
    """
    assert isinstance(backend_config, QuantinuumConfig), (
        "Operation only supported for QuantinuumConfig."
    )

    res = get_nexus_client().get(
        f"/api/machines/v1beta/{backend_config.device_name}/status",
    )
    if res.status_code != 200:
        raise ResourceFetchFailed(message=res.text, status_code=res.status_code)

    return DeviceStateEnum(res.json()["state"])


def _get_backend_property(
    backend_config: BackendConfig,
    backend_property: Literal[
        "supports_shots",
        "supports_counts",
        "supports_state",
        "supports_unitary",
        "supports_density_matrix",
        "supports_expectation",
        "expectation_allows_nonhermitian",
        "supports_contextual_optimisation",
    ],
) -> bool:
    """Retrieves a Backend property for a given BackendConfig."""

    res = get_nexus_client().post(
        "/api/v5/backend_info/backend_property",
        json={
            "backend_config": backend_config.model_dump(mode="json"),
            "property": backend_property,
        },
    )
    if res.status_code != 200:
        raise ResourceFetchFailed(message=res.text, status_code=res.status_code)

    property_value: bool = res.json()

    return property_value
