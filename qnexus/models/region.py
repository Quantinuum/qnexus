"""Region model for QNexus API client."""

import os
import warnings
from typing import Literal

from qnexus.config import CONFIG
from qnexus.models.utils import assert_never

Region = Literal["us", "sg"]


def get_hostname(region: Region) -> str:
    """Get the hostname for a given region."""

    # Use environment variable override if set, otherwise fall back to defaults
    hostname_override = os.getenv(f"NEXUS_{region.upper()}_DOMAIN")
    if hostname_override:
        return hostname_override

    if region == "us":
        return "nexus.quantinuum.com"
    if region == "sg":
        return "nexus.quantinuum.sg"
    raise ValueError(f"Invalid region: {region}")


def _get_home_region() -> Region:
    """Infer the home region for the current environment from the domain."""

    match CONFIG.domain:
        case "nexus.quantinuum.com":
            return "us"
        case "nexus.quantinuum.sg":
            return "sg"
        case _:
            raise ValueError(f"Unknown home region: {CONFIG.domain}")


def _get_costing_system_for_region(
    region: Region | None = None,
) -> str:
    """Get the default costing system name for a given region.
    Internal only function to be used before setting an automatic system is deprecated.
    """

    warnings.warn(
        "system_name is unset so defaulting based on region. system_name will be required in a future release.",
        category=DeprecationWarning,
    )

    if region is None:
        region = _get_home_region()

    match region:
        case "us":
            return "Helios-1"
        case "sg":
            return "Helios-2"
        case _:
            assert_never(region)
