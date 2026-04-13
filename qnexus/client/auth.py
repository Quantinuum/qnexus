"""Client API for authentication in Nexus."""

import datetime
import getpass
import time
import warnings
import webbrowser
from http import HTTPStatus

import httpx
import jwt
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
        return False
    # Check expiry of refresh token (assume JWT)
    try:
        payload = jwt.decode(refresh_token, options={"verify_signature": False})
        exp = payload.get("exp")
        if exp:
            expiry_dt = datetime.datetime.fromtimestamp(exp)
            now = datetime.datetime.now()
            hours_left = (expiry_dt - now).total_seconds() / 3600
            if hours_left < 24:
                msg = (
                    f"Your refresh token expires in less than 24 hours (expires at {expiry_dt}). "
                    "You will need to login again after this time or use force=True to refresh now."
                )
                warnings.warn(msg, category=UserWarning)
    except jwt.PyJWTError:
        pass
    # Try a lightweight authenticated request to check validity
    try:
        client = get_nexus_client()
        resp = client.get("/api/users/v1beta2/me")
        if resp.status_code == HTTPStatus.OK:
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


def login(force: bool = False, region: Region | None = None) -> None:
    """
    Log in to Quantinuum Nexus using the web browser.

    (if web browser can't be launched, displays the link)
    """
    different_domain = False
    if region is not None:
        domain = get_hostname(region)
        if domain != CONFIG.domain:
            different_domain = True
            CONFIG.domain = domain

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
    """Log in to Nexus using a username and password."""
    different_domain = False
    if region is not None:
        domain = get_hostname(region)
        if domain != CONFIG.domain:
            different_domain = True
            CONFIG.domain = domain

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
    different_domain = False
    if region is not None:
        domain = get_hostname(region)
        if domain != CONFIG.domain:
            different_domain = True
            CONFIG.domain = domain

    if not force and not different_domain and is_logged_in():
        print("Already logged in. Tokens are valid.")
        return
    _request_tokens(user=user, pwd=pwd)
    print(f"✅ Successfully logged in as {user}.")


def logout() -> None:
    """Clear tokens from file system and the client."""
    remove_token("refresh_token")
    remove_token("access_token")
    get_nexus_client(reload=True)
    print("Successfully logged out.")


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
        get_nexus_client(reload=True)

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
