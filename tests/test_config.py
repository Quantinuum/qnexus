"""Tests for qnexus config loading behavior."""

import importlib
from pathlib import Path

import pytest

from qnexus.config import Config, _resolve_env_file


def test_config_can_be_loaded_from_explicit_env_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`Config` should read values from an explicit env file path."""
    monkeypatch.delenv("NEXUS_DOMAIN", raising=False)
    monkeypatch.delenv("NEXUS_HOST", raising=False)
    config_file = tmp_path / "qnexus.env"
    config_file.write_text("NEXUS_DOMAIN=example.test\nNEXUS_PORT=8443\n")

    config = Config(_env_file=str(config_file), _env_file_encoding="utf-8")

    assert config.domain == "example.test"
    assert config.port == 8443


def test_resolve_env_file_uses_nexus_config_file_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`NEXUS_CONFIG_FILE` should override the default env file path."""
    monkeypatch.setenv("NEXUS_CONFIG_FILE", "~/.qnexus/custom")
    assert _resolve_env_file() == str(Path.home() / ".qnexus" / "custom")


def test_module_config_uses_resolved_env_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Module-level `CONFIG` should load values from `NEXUS_CONFIG_FILE`."""
    config_file = tmp_path / "qnexus.config"
    config_file.write_text("NEXUS_DOMAIN=from-file.test\n")

    import qnexus.config as config_module

    try:
        monkeypatch.delenv("NEXUS_DOMAIN", raising=False)
        monkeypatch.delenv("NEXUS_HOST", raising=False)
        monkeypatch.setenv("NEXUS_CONFIG_FILE", str(config_file))
        config_module = importlib.reload(config_module)
        assert config_module.CONFIG.domain == "from-file.test"
    finally:
        monkeypatch.delenv("NEXUS_CONFIG_FILE", raising=False)
        importlib.reload(config_module)
