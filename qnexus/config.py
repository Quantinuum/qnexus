"""Quantinuum Nexus API client configuration via pydantic-settings."""

from pathlib import Path
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    """QNexus Configuration schema.

    Uses pydantic-settings to read environment variables for qnexus configuration."""

    model_config = SettingsConfigDict(env_prefix="NEXUS_")

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
    absolute_token_path: str | None = None

    @property
    def resolved_token_path(self) -> Path:
        """Resolve token path from token_path and absolute_token_path."""
        if self.absolute_token_path is not None:
            return Path(self.absolute_token_path)
        return Path(Path.home(), self.token_path)

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
