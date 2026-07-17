"""Client API for authentication in Nexus."""

import datetime
import getpass
import time
import warnings
import webbrowser
from http import HTTPStatus

import httpx
from colorama import Fore
from pydantic import EmailStr
from rich.console import Console
from rich.panel import Panel

import qnexus.exceptions as qnx_exc
from qnexus.client import (
    VERSION,
    VERSION_HEADER,
    _check_version_headers,
    get_nexus_client,
)
from qnexus.client.utils import consolidate_error, read_token, remove_token, write_token
from qnexus.config import CONFIG
from qnexus.models.region import Region, get_hostname

console = Console()


def is_logged_in() -> bool:
    """Check if the user is already logged in by verifying tokens and
    attempting a lightweight authenticated request."""

    try:
        refresh_token = read_token("refresh_token")
        access_token = read_token("access_token")

        # Check that tokens are present
        if not refresh_token or not access_token:
            return False
    except FileNotFoundError:
        # If tokens aren't on disk, fall through to the network check
        # in case we have valid in-memory tokens (e.g. store_tokens=False).
        pass

    try:
        # Check expiry of refresh token, additionally checking authentication by making a request
        exp = get_token_expiry()

        hours_left = exp / 3600
        if hours_left < 24:
            expiry_dt = datetime.datetime.now() + datetime.timedelta(seconds=exp)
            msg = (
                f"Your refresh token expires in less than 24 hours (expires at {expiry_dt}). "
                "You will need to login again after this time or use qnx.login(force=True) to refresh now."
            )
            warnings.warn(msg, category=UserWarning)
        return True
    except (httpx.HTTPError, qnx_exc.AuthenticationError):
        pass
    return False


def _get_auth_client() -> httpx.Client:
    """Getter function for the Nexus auth client."""
    return httpx.Client(
        base_url=f"{CONFIG.url}/auth",
        timeout=None,
        verify=CONFIG.httpx_verify,
    )


def _update_domain_for_region(region: Region | None) -> bool:
    """Update configured domain for a region and report whether it changed."""
    if region is None:
        return False

    domain = get_hostname(region)
    if domain != CONFIG.domain:
        CONFIG.domain = domain
        return True

    return False


def login(force: bool = False, region: Region | None = None) -> None:
    """
    Log in to Quantinuum Nexus using the web browser.

    (if web browser can't be launched, displays the link)

    Examples:
        >>> import qnexus as qnx
        >>> qnx.auth.login()

        >>> qnx.auth.login(force=True)  # Force re-authentication
    """
    different_domain = _update_domain_for_region(region)

    if not force and not different_domain and is_logged_in():
        print("Already logged in. Tokens are valid.")
        return

    res = _get_auth_client().post(
        "/device/device_authorization",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={"client_id": "scales", "scope": "myqos"},
    )

    user_code = res.json()["user_code"]
    device_code = res.json()["device_code"]
    verification_uri_complete = res.json()["verification_uri_complete"]
    expires_in = res.json()["expires_in"]
    poll_interval = res.json()["interval"]

    webbrowser.open(verification_uri_complete, new=2)

    token_request_body = {
        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        "device_code": device_code,
        "client_id": "scales",
    }

    print("🌐 Browser log in initiated.")

    console.print(
        Panel(
            f"""
        Confirm that the browser shows the following code and click 'allow device':

                                     {user_code}
        """,
            width=90,
        )
    )

    print(
        "Browser didn't open automatically? Use this link: "
        f"{Fore.BLUE + verification_uri_complete}"
    )

    polling_for_seconds = 0
    while polling_for_seconds < expires_in:
        time.sleep(poll_interval)
        polling_for_seconds += poll_interval
        resp = _get_auth_client().post(
            "/device/token",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                VERSION_HEADER: VERSION,
            },
            data=token_request_body,
        )
        if (
            resp.status_code == HTTPStatus.BAD_REQUEST
            and resp.json().get("error") == "AUTHORIZATION_PENDING"
        ):
            continue
        if resp.status_code == HTTPStatus.TOO_MANY_REQUESTS:
            continue
        if resp.status_code == HTTPStatus.OK:
            resp_json = resp.json()
            write_token("refresh_token", resp_json["refresh_token"])
            write_token(
                "access_token",
                resp_json["access_token"],
            )
            get_nexus_client(reload=True)
            # spinner.stop()
            print(
                f"✅ Successfully logged in as {resp_json['email']} using the browser."
            )
            _check_version_headers(resp)
            return
        # Fail for all other statuses
        consolidate_error(res=resp, description="Browser Login")
        # spinner.stop()

        return
    raise qnx_exc.AuthenticationError("Browser login Failed, code has expired.")


def login_with_credentials(force: bool = False, region: Region | None = None) -> None:
    """Log in to Nexus using a username and password.

    Examples:
        >>> import qnexus as qnx
        >>> qnx.auth.login_with_credentials()
    """
    different_domain = _update_domain_for_region(region)

    if not force and not different_domain and is_logged_in():
        print("Already logged in. Tokens are valid.")
        return
    user_name = input("Enter your Nexus email: ")
    pwd = getpass.getpass(prompt="Enter your Nexus password: ")

    _request_tokens(user=user_name, pwd=pwd)

    print(f"✅ Successfully logged in as {user_name}.")


def login_no_interaction(
    user: EmailStr, pwd: str, force: bool = False, region: Region | None = None
) -> None:
    """Log in to Nexus using a username and password.
    Please be careful with storing credentials in plain text or source code.
    """
    different_domain = _update_domain_for_region(region)

    if not force and not different_domain and is_logged_in():
        print("Already logged in. Tokens are valid.")
        return
    _request_tokens(user=user, pwd=pwd)
    print(f"✅ Successfully logged in as {user}.")


def logout() -> None:
    """Clear tokens from file system and the client.

    Examples:
        >>> import qnexus as qnx
        >>> qnx.auth.logout()
    """
    remove_token("refresh_token")
    remove_token("access_token")
    get_nexus_client(reload=True)
    print("Successfully logged out.")


def login_with_token(refresh_token: str) -> None:
    """Authenticate using a refresh token held in memory.

    Sets the token on the current client's auth handler and exchanges
    it for a fresh access token.  No tokens are written to disk.

    This is intended for programmatic use where the caller manages
    token storage externally (e.g. multiple accounts).

    **Multi-process usage:** Each Python process has its own client
    instance, so separate processes can each call ``login_with_token``
    with different user tokens without interfering with each other.
    Set ``CONFIG.store_tokens = False`` to prevent other code paths
    (e.g. automatic token refresh) from writing to the shared
    ``~/.qnx/auth/`` directory.

    **Single-process token hot-swapping:** You can switch between
    users sequentially within a single process. All subsequent API
    calls will use the most recently set token::

        import qnexus as qnx
        from qnexus.config import CONFIG
        CONFIG.store_tokens = False

        alice_token = "..."
        bob_token = "..."

        qnx.login_with_token(alice_token)
        qnx.projects.get_all()  # runs as alice

        qnx.login_with_token(bob_token)
        qnx.projects.get_all()  # runs as bob

    .. warning::
        This function is **not thread-safe**. The client and its auth
        cookies are shared process-wide without locking. If one thread
        calls ``login_with_token(alice_token)`` while another thread is
        mid-request as Bob, the cookies can be in an inconsistent state.
        For concurrent multi-user workloads, use separate processes
        rather than threads within a single process.

    """

    client = get_nexus_client(reload=True)
    client.auth.set_tokens(refresh_token)  # type: ignore[union-attr]


def _request_tokens(user: EmailStr, pwd: str) -> None:
    """Method to send login request to Nexus auth api and save tokens."""
    body = {"email": user, "password": pwd}
    try:
        resp = _get_auth_client().post(
            "/login",
            json=body,
            headers={VERSION_HEADER: VERSION},
        )

        mfa_redirect_uri = resp.json().get("redirect_uri", "")
        if mfa_redirect_uri.startswith("/auth/mfa_challenge/"):
            mfa_code = input("Enter your MFA verification code: ")
            body["code"] = mfa_code
            body.pop("password")
            resp = _get_auth_client().post(
                "/mfa_challenge",
                json=body,
            )

        terms_redirect_uri = resp.json().get("redirect_uri", "")
        if terms_redirect_uri.startswith("/auth/terms_challenge"):
            message = "Terms and conditions not accepted. To continue, "
            message += "please accept our new terms and conditions by signing in "
            message += "to the Nexus website https://nexus.quantinuum.com/auth/login."

            # logger.error(message)
            raise qnx_exc.AuthenticationError(message)

        _response_check(resp, "Login")

        myqos_oat = resp.cookies.get("myqos_oat", None)
        myqos_id = resp.cookies.get("myqos_id", None)

        if not myqos_oat or not myqos_id:
            raise qnx_exc.AuthenticationError(
                "Authorization cookies missing from response."
            )

        write_token("refresh_token", myqos_oat)
        write_token("access_token", myqos_id)
        client = get_nexus_client(reload=True)
        # Set tokens directly in memory so auth works even when
        # store_tokens=False (where write_token is a no-op).
        client.auth.cookies.set("myqos_oat", myqos_oat, domain=CONFIG.domain)  # type: ignore[union-attr]
        client.auth.cookies.set("myqos_id", myqos_id, domain=CONFIG.domain)  # type: ignore[union-attr]

        _check_version_headers(resp)

    finally:
        del user
        del pwd
        del body


def _response_check(res: httpx.Response, description: str) -> None:
    """Consolidate as much error-checking of response"""
    # check if token has expired or is generally unauthorized
    resp_json = res.json()
    if res.status_code == HTTPStatus.UNAUTHORIZED:
        raise qnx_exc.AuthenticationError(
            (
                f"Authorization failure attempting: {description}."
                f"\n\nServer Response: {resp_json}"
            )
        )
    if res.status_code != HTTPStatus.OK:
        raise qnx_exc.AuthenticationError(
            f"HTTP error attempting: {description}.\n\nServer Response: {resp_json}"
        )


def get_token_expiry() -> int:
    """Get the time-to-live/expiry of the current refresh token (OAT) in seconds."""
    resp = get_nexus_client().get("/auth/tokens")
    ttl = resp.json()["token_status"]["ttl"]

    if not isinstance(ttl, int):
        raise RuntimeError(f"Expected integer TTL, got {type(ttl).__name__}: {ttl}")
    return ttl
