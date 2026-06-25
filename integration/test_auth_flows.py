"""Test basic functionality relating to the auth module."""

from contextlib import redirect_stdout
from io import StringIO
from typing import Any

import pytest
from httpx import ConnectError

import qnexus as qnx
from qnexus.client import get_nexus_client
from qnexus.client.auth import login_no_interaction
from qnexus.client.utils import read_token
from qnexus.config import CONFIG
from qnexus.exceptions import AuthenticationError


def test_credential_login_full_flow(
    monkeypatch: Any,
) -> None:
    """Test that we can delete access tokens, login using credentials and
    delete tokens once again."""
    username = CONFIG.qa_user_email
    pwd = CONFIG.qa_user_password

    qnx.logout()

    if CONFIG.store_tokens:
        with pytest.raises(FileNotFoundError):
            read_token(token_type="access_token")
            read_token(token_type="refresh_token")

    with pytest.raises(AuthenticationError):
        qnx.users.get_self()

    # fake user input from stdin
    monkeypatch.setattr("sys.stdin", StringIO(username + "\n"))
    monkeypatch.setattr("getpass.getpass", lambda prompt: pwd)

    qnx.login_with_credentials()

    if CONFIG.store_tokens:
        assert read_token(token_type="access_token") != ""
        assert read_token(token_type="refresh_token") != ""

    # Verify authentication works regardless of token storage mode
    qnx.users.get_self()

    qnx.logout()

    if CONFIG.store_tokens:
        with pytest.raises(FileNotFoundError):
            read_token(token_type="access_token")
            read_token(token_type="refresh_token")

    with pytest.raises(AuthenticationError):
        qnx.users.get_self()

    # Login again to make sure credentials are in the system for the other tests
    login_no_interaction(username, pwd, force=True)


@pytest.mark.skip(reason="Not implemented")
def test_device_code_flow_login_full_flow() -> None:
    """Test the flow for logging in with the browser."""


def test_domain_switch() -> None:
    """Set that we can reset the domain, login and not
    for tokens/URL to be dynamically loaded."""

    username = CONFIG.qa_user_email
    pwd = CONFIG.qa_user_password

    login_no_interaction(username, pwd)

    qnx.users.get_self()

    original_domain = CONFIG.domain

    # fake domain will reset the client value
    qnx.logout()
    fake_domain = "fake_nexus.com"
    CONFIG.domain = fake_domain
    assert fake_domain in str(get_nexus_client(reload=True).base_url)

    with pytest.raises(ConnectError):
        qnx.users.get_self()

    # setting it again will update the client without any restart required
    CONFIG.domain = original_domain
    login_no_interaction(username, pwd)
    assert original_domain in str(get_nexus_client().base_url)

    qnx.users.get_self()


def test_login_when_already_logged_in(monkeypatch: Any) -> None:
    """Test that logging in when already logged in notifies the user appropriately."""
    username = CONFIG.qa_user_email
    pwd = CONFIG.qa_user_password

    # Ensure logged out first
    qnx.logout()
    # First login
    monkeypatch.setattr("sys.stdin", StringIO(username + "\n"))
    monkeypatch.setattr("getpass.getpass", lambda prompt: pwd)
    qnx.login_with_credentials()

    # Try to login again, should indicate already logged in
    # Capture output if function prints, or check for raised exception/message
    output = StringIO()
    with redirect_stdout(output):
        qnx.login_with_credentials()
    out_str = output.getvalue()
    assert "already logged in" in out_str.lower()
