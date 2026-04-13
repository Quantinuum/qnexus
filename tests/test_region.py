"""Tests for region hostname resolution."""

import pytest

from qnexus.models.region import get_hostname


def test_get_hostname_defaults() -> None:
    """Falls back to built-in hostnames when no overrides are set."""
    assert get_hostname("us") == "nexus.quantinuum.com"
    assert get_hostname("sg") == "nexus.quantinuum.sg"


def test_get_hostname_uses_region_environment_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Use NEXUS_<REGION>_DOMAIN when provided for a region."""
    monkeypatch.setenv("NEXUS_US_DOMAIN", "custom.us.example.com")
    monkeypatch.setenv("NEXUS_SG_DOMAIN", "custom.sg.example.com")

    assert get_hostname("us") == "custom.us.example.com"
    assert get_hostname("sg") == "custom.sg.example.com"
