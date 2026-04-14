"""Quantinuum Nexus API client configuration via pydantic-settings."""

import os

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _resolve_env_file() -> str:
    """Resolve the settings env file path.

    Supports an explicit override via ``NEXUS_CONFIG_FILE`` and defaults to
    ``~/.qnexus/config``.
    """
    return os.path.expanduser(os.getenv("NEXUS_CONFIG_FILE", "~/.qnexus/config"))


class Config(BaseSettings):
    """QNexus Configuration schema.

    Uses pydantic-settings to read environment variables for qnexus configuration."""

    model_config = SettingsConfigDict(
        env_prefix="NEXUS_",
        env_file=_resolve_env_file(),
    )

    # web
    protocol: str = "https"
    websockets_protocol: str = "wss"
    domain: str = Field(
        validation_alias=AliasChoices("NEXUS_DOMAIN", "NEXUS_HOST"),
        default="nexus.quantinuum.com",
    )
    port: int = 443
    httpx_verify: bool = True

    # auth
    store_tokens: bool = True  # Not implemented
    token_path: str = ".qnx/auth"

    # testing
    qa_user_email: str = ""
    qa_user_password: str = ""

    def __str__(self) -> str:
        """String representation of current config."""
        return self.model_dump_json()

    @property
    def url(self) -> str:
        """Current http API URL"""
        return f"{self.protocol}://{self.domain}:{self.port}"

    @property
    def websockets_url(self) -> str:
        """Current websockets API URL"""
        return f"{self.websockets_protocol}://{self.domain}:{self.port}"


CONFIG = Config()
