"""Region model for QNexus API client."""

import os
from typing import Literal

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
