"""Test the token-based auth logic for the httpx Client.

N.B. these manipulate environment variables so currently run in isolation via scripts/run_unit_test.sh.
"""

from typing import Any, Generator
from uuid import uuid4

import httpx
import pytest
import respx

import qnexus as qnx
from qnexus.client import _nexus_client, get_nexus_client
from qnexus.client.utils import read_token, remove_token, write_token
from qnexus.config import CONFIG
from qnexus.exceptions import AuthenticationError


@pytest.fixture(autouse=True)
def clean_token_state() -> Generator[Any, Any, Any]:
    """Clean up token state before and after each test."""
    # Setup - clean token files
    remove_token("refresh_token")
    remove_token("access_token")
    global _nexus_client
    if _nexus_client is not None:
        _nexus_client.close()
        _nexus_client = None

    # Store tokens in a temporary location
    old_token_path = CONFIG.token_path
    CONFIG.token_path = f"/tmp/qnexus_tests/{str(uuid4())}"

    yield  # Run the test

    # Teardown - clean up after test
    remove_token("refresh_token")
    remove_token("access_token")
    get_nexus_client(reload=True)
    CONFIG.token_path = old_token_path


@respx.mock
def test_token_refresh() -> None:
    """Test the auth refresh logic, using in-memory token storage.

    Test that we can refresh the access token using the refresh token
    and that the new access token is used in subsequent requests.
    """

    old_id_token = "dummy_id"
    refreshed_access_token = "new_dummy_id"

    write_token("refresh_token", "dummy_oat")
    write_token("access_token", old_id_token)

    # Mock the list projects endpoint to force a refresh
    list_project_route = respx.get(
        f"{get_nexus_client().base_url}/api/projects/v1beta2"
    ).mock(
        side_effect=[
            httpx.Response(401),
            httpx.Response(200, json={"included": {}, "data": []}),
        ]
    )

    # Mock the refresh endpoint
    refresh_token_route = respx.post(
        f"{get_nexus_client().base_url}/auth/tokens/refresh"
    ).mock(
        return_value=httpx.Response(
            200,
            headers={
                "set-cookie": f"myqos_id={refreshed_access_token}; "
                "HttpOnly; Path=/; SameSite=Lax; Secure"
            },
        )
    )

    qnx.projects.get_all().list()

    assert list_project_route.called
    assert refresh_token_route.called

    # Confirm that the access token was updated
    assert read_token("access_token") == refreshed_access_token

    # confirm that the request headers were updated
    first_cookie_header = list_project_route.calls[0].request.headers["cookie"]
    assert f"myqos_id={old_id_token}" in first_cookie_header

    last_cookie_header = list_project_route.calls[-1].request.headers["cookie"]
    assert f"myqos_id={refreshed_access_token}" in last_cookie_header


@respx.mock
def test_token_refresh_expired() -> None:
    """Test the case of an expired refresh token, using in-memory token storage."""

    write_token("refresh_token", "dummy_oat")
    write_token("access_token", "dummy_id")

    # Mock the list projects endpoint to force a refresh
    list_project_route = respx.get(
        f"{get_nexus_client().base_url}/api/projects/v1beta2"
    ).mock(return_value=httpx.Response(401))

    # Mock the expiry of the refresh token
    refresh_token_route = respx.post(
        f"{get_nexus_client().base_url}/auth/tokens/refresh"
    ).mock(return_value=httpx.Response(401))

    with pytest.raises(AuthenticationError):
        qnx.projects.get_all().list()

    assert list_project_route.called
    assert refresh_token_route.called


def test_nexus_client_reloads_domain() -> None:
    """Test the reload functionality of the nexus client.
    We should be able to change the domain in the config
    and have the client reload with the new domain obtainable
    via a getter function.
    """

    domain_one = "dummy_domain_one.com"
    domain_two = "dummy_domain_two.com"

    CONFIG.domain = domain_one
    # mock login
    write_token("refresh_token", "dummy_oat")
    write_token("access_token", "dummy_id")

    client_one = get_nexus_client(reload=True)
    client_two = get_nexus_client(reload=True)

    assert domain_one in str(client_one.base_url)
    assert domain_one in str(client_two.base_url)

    CONFIG.domain = domain_two

    assert domain_two not in str(client_one.base_url)
    assert domain_two not in str(client_two.base_url)

    client_two = get_nexus_client(reload=True)
    # client_two getter should not effect client_one
    assert domain_two not in str(client_one.base_url)
    # client_two getter should reload the client
    assert domain_two in str(client_two.base_url)
