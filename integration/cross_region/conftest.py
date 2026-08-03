"""Fixtures shared across the cross-region job submission tests.

Required env vars to run this suite

``NEXUS_CROSS_REGION_TESTS``  set (to any value) to enable this suite.
``NEXUS_HOME_REGION``         region to log in against (default: "sg").
``NEXUS_TARGET_REGION``       region job submissions are targeted at (default: "us").
``NEXUS_QA_HOME_USER_EMAIL``  user with cross region access
``NEXUS_QA_HOME_USER_PASSWORD``  user creds with cross region access
"""

import os
from typing import Generator

import pytest

import qnexus as qnx
from qnexus.client.auth import login_no_interaction
from qnexus.config import CONFIG
from qnexus.models.region import Region


def pytest_collection_modifyitems(
    items: list[pytest.Item], config: pytest.Config
) -> None:
    """Skip all cross_region tests when NEXUS_CROSS_REGION_TESTS env var is not set."""
    if os.getenv("NEXUS_CROSS_REGION_TESTS") is not None:
        return

    skip = pytest.mark.skip(
        reason="Cross-region tests skipped: NEXUS_CROSS_REGION_TESTS env var not set."
    )
    for item in items:
        if "cross_region" in str(item.path):
            item.add_marker(skip)


@pytest.fixture(scope="module")
def home_region() -> Region:
    """The region the test user logs in against."""
    return os.getenv("NEXUS_HOME_REGION", "sg")


@pytest.fixture(scope="module")
def target_region() -> Region:
    """The region that jobs are submitted to from the home region."""
    return os.getenv("NEXUS_TARGET_REGION", "us")


@pytest.fixture(scope="module", autouse=True)
def authenticated_nexus(home_region: Region) -> Generator[None, None, None]:
    """Override `authenticated_nexus` to log in against `home_region`, instead of 
    the default region used by the rest of the integration suite."""
    try:
        login_no_interaction(
            CONFIG.qa_home_user_email, CONFIG.qa_home_user_password, region=home_region
        )
        yield
    finally:
        qnx.auth.logout()
