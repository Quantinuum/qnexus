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


class AuthHandler(httpx.Auth):
    """Custom nexus auth handler"""

    cookies: httpx.Cookies

    def __init__(self) -> None:
        self.cookies = httpx.Cookies()
        self.reload_tokens()

        super().__init__()

    def reload_tokens(self) -> None:
        """Clear tokens and attempt to reload from the file system."""
        try:
            self.cookies.clear()
            token = read_token("refresh_token")
            self.cookies.set("myqos_oat", token, domain=CONFIG.domain)
            id_token = read_token("access_token")
            self.cookies.set("myqos_id", id_token, domain=CONFIG.domain)
        except FileNotFoundError:
            pass

    def auth_flow(
        self, request: httpx.Request
    ) -> typing.Generator[httpx.Request, httpx.Response, None]:
        self.cookies.set_cookie_header(request)

        response = yield request

        _check_sunset_header(request, response)

        if response.status_code == 401:
            if self.cookies.get("myqos_oat") is None:
                try:
                    token = read_token(
                        "refresh_token",
                    )
                    self.cookies.set("myqos_oat", token, domain=CONFIG.domain)
                except FileNotFoundError as exc:
                    raise AuthenticationError(
                        "Not authenticated. Please run `qnx login` in your terminal."
                    ) from exc

            auth_response = yield self.build_refresh_request()
            if auth_response.status_code == 401:
                raise AuthenticationError(
                    "Not authenticated. Please run `qnx login` in your terminal."
                )

            auth_response.raise_for_status()
            self.cookies.extract_cookies(auth_response)

            write_token(
                "access_token",
                self.cookies.get("myqos_id", domain=CONFIG.domain) or "",
            )
            if request.headers.get("cookie"):
                request.headers.pop("cookie")
            self.cookies.set_cookie_header(request)

            _check_version_headers(auth_response)
            yield request

    def build_refresh_request(self) -> httpx.Request:
        """Build the request for refreshing the id token."""
        self.cookies.delete("myqos_id")  # We need to delete any existing id token first
        return httpx.Request(
            method="POST",
            url=f"{CONFIG.url}/auth/tokens/refresh",
            cookies=self.cookies,
            headers={VERSION_HEADER: VERSION},
        )

    def refresh_id_token(self) -> None:
        """Refresh the myqos_id token using the refresh token.

        Sends a refresh request to the auth endpoint using the stored
        myqos_oat cookie, updates the in-memory cookies and persists
        the new access token to the filesystem.

        Returns:
            The new myqos_id token value.

        Raises:
            AuthenticationError: If no refresh token is available or
                the refresh request fails.
        """
        if self.cookies.get("myqos_oat") is None:
            try:
                token = read_token("refresh_token")
                self.cookies.set("myqos_oat", token, domain=CONFIG.domain)
            except FileNotFoundError as exc:
                raise AuthenticationError(
                    "Not authenticated. Please run `qnx login` in your terminal."
                ) from exc

        response = httpx.post(
            f"{CONFIG.url}/auth/tokens/refresh",
            cookies=self.cookies,
            headers={VERSION_HEADER: VERSION},
            verify=CONFIG.httpx_verify,
        )

        if response.status_code == 401:
            raise AuthenticationError(
                "Not authenticated. Please run `qnx login` in your terminal."
            )
        response.raise_for_status()

        self.cookies.extract_cookies(response)

        new_token = self.cookies.get("myqos_id", domain=CONFIG.domain) or ""
        write_token("access_token", new_token)


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
        _auth_handler.reload_tokens()

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
