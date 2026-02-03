"""Client API for Nexus."""

import typing
import warnings
from importlib.metadata import version
from urllib.parse import urlparse

import httpx

from qnexus.client.utils import read_token, write_token
from qnexus.config import CONFIG
from qnexus.exceptions import AuthenticationError

# Used by the client to identify its own version when refreshing auth token
# Example value: 0.23.0
VERSION_HEADER = "X-qnexus-version"

# Used by the server to specify the latest version
# Example value: 1.0.0
LATEST_VERSION_HEADER = "X-qnexus-version-latest"

# Used by the server to indicate the status of a version
# Example value: 0.23.0; deprecated
VERSION_STATUS_HEADER = "X-qnexus-version-status"

VERSION = version("qnexus")


def get_cookies_from_disk() -> httpx.Cookies:
    cookies = httpx.Cookies()
    try:
        refresh_token = read_token("refresh_token")
        cookies.set("myqos_oat", refresh_token, domain=CONFIG.domain)
    except FileNotFoundError:
        pass
    try:
        access_token = read_token("access_token")
        cookies.set("myqos_id", access_token, domain=CONFIG.domain)
    except FileNotFoundError:
        pass

    return cookies


def set_cookie_header(cookies: httpx.Cookies, request: httpx.Request) -> None:
    """by default cookies.set_cookie_header(...) doesn't overwrite cookies if they already exist in the request header"""
    if request.headers.get("cookie"):
        request.headers.pop("cookie")
    cookies.set_cookie_header(request)


class AuthHandler(httpx.Auth):
    """Custom nexus auth handler"""

    def auth_flow(
        self, request: httpx.Request
    ) -> typing.Generator[httpx.Request, httpx.Response, None]:
        cookies = get_cookies_from_disk()
        set_cookie_header(cookies, request)
        response = yield request

        _check_sunset_header(request, response)

        if response.status_code == 401:
            auth_response = yield httpx.Request(
                method="POST",
                url=f"{CONFIG.url}/auth/tokens/refresh",
                cookies=cookies,
                headers={VERSION_HEADER: VERSION},
            )

            if auth_response.status_code == 401:
                raise AuthenticationError(
                    "Not authenticated. Please run `qnx login` in your terminal."
                )

            auth_response.raise_for_status()
            auth_response_cookies = httpx.Cookies()
            auth_response_cookies.extract_cookies(auth_response)

            write_token(
                "access_token",
                auth_response_cookies.get("myqos_id") or "",
            )

            _check_version_headers(auth_response)
            set_cookie_header(auth_response_cookies, request)

            yield request


_nexus_client: httpx.Client | None = None


def get_nexus_client(reload: bool = False) -> httpx.Client:
    """Getter function for the nexus client.
    Args:
        reload: If True, reconstruct the client (and auth tokens).
    Returns:
        httpx.Client: The nexus client.
    """
    global _nexus_client
    if _nexus_client is None or reload:
        _auth_handler = AuthHandler()
        _nexus_client = httpx.Client(
            base_url=CONFIG.url,
            auth=_auth_handler,
            timeout=None,
            verify=CONFIG.httpx_verify,
        )
    return _nexus_client


def _check_sunset_header(request: httpx.Request, response: httpx.Response) -> None:
    sunset_header = response.headers.get("sunset")
    path = urlparse(str(request.url)).path
    if sunset_header:
        warnings.warn(
            f"Your version of qnexus is using a deprecated API endpoint ({path}) that will be deleted on {sunset_header}. "
            "After this date your current qnexus version may stop functioning. Please update to a later qnexus version to resolve the issue.",
            category=DeprecationWarning,
        )


def _check_version_headers(response: httpx.Response) -> None:
    latest_version = response.headers.get(LATEST_VERSION_HEADER)
    version_status = response.headers.get(VERSION_STATUS_HEADER)
    if latest_version != VERSION and version_status:
        try:
            _version, status = [s.strip() for s in version_status.split(";")]
        except ValueError:
            return
        if status.lower() not in ("current", "ok"):
            warnings.warn(
                f"Your qnexus client version is {VERSION}, which is {status}.\nVersion {latest_version} is available. Please consider upgrading.",
                category=DeprecationWarning,
            )
