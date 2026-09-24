"""Region model for QNexus API client."""

import os
import warnings
from typing import Literal

from qnexus.config import CONFIG
from qnexus.models.utils import assert_never

Region = Literal["us", "sg"]

PROD_US_DOMAIN = "nexus.quantinuum.com"
PROD_SG_DOMAIN = "nexus.quantinuum.sg"

# The backend has no notion of the whitelabel domain, so any response content referencing the
# backing domain (e.g. auth verification links) needs to be rewritten to the whitelabel domain.
_WHITELABEL_SUFFIX = "-nexus.quantinuum.com"


def _get_whitelabel_backing_domain(domain: str) -> str | None:
    """Return the backing domain for a whitelabel domain, or None if not one."""
    if domain.endswith(_WHITELABEL_SUFFIX):
        return PROD_US_DOMAIN
    return None


def _rewrite_verification_uri(verification_uri_complete: str) -> str:
    """Rewrite a verification URI to the configured whitelabel domain, if any."""
    backing_domain = _get_whitelabel_backing_domain(CONFIG.domain)
    if backing_domain and backing_domain in verification_uri_complete:
        return verification_uri_complete.replace(backing_domain, CONFIG.domain)
    return verification_uri_complete


def get_hostname(region: Region) -> str:
    """Get the hostname for a given region."""

    # Use environment variable override if set, otherwise fall back to defaults
    hostname_override = os.getenv(f"NEXUS_{region.upper()}_DOMAIN")
    if hostname_override:
        return hostname_override

    if region == "us":
        return PROD_US_DOMAIN
    if region == "sg":
        return PROD_SG_DOMAIN
    raise ValueError(f"Invalid region: {region}")


def _get_home_region() -> Region:
    """Infer the home region for the current environment from the domain."""

    match CONFIG.domain:
        case domain if domain == PROD_US_DOMAIN:
            return "us"
        case domain if domain == PROD_SG_DOMAIN:
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
