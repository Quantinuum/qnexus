"""Helper to load per-region device names for cross-region integration tests."""

import json
from pathlib import Path
from typing import cast

_CROSS_REGION_DIR = Path(__file__).parent
_REGION_CONFIG_PATH = _CROSS_REGION_DIR / "region_config.json"


def _load_config() -> dict[str, dict[str, str]]:
    with open(_REGION_CONFIG_PATH) as f:
        return cast(dict[str, dict[str, str]], json.load(f))


_ALL_REGION_CONFIGS: dict[str, dict[str, str]] = _load_config()


class _DeviceValidationDict(dict[str, str]):
    """A dict of devices for a region that raises a helpful error if a
    requested device hasn't been configured for that region."""

    def __getitem__(self, key: str) -> str:
        value = dict.__getitem__(self, key)
        if not value or not value.strip():
            raise ValueError(
                f"Device '{key}' is not configured for this region. "
                "Please update integration/cross_region/region_config.json."
            )
        return value


def load_region_devices(region: str) -> dict[str, str]:
    """Return the device/system names configured for the given region."""

    if region not in _ALL_REGION_CONFIGS:
        raise ValueError(
            f"Unknown region '{region}'. Valid regions: {list(_ALL_REGION_CONFIGS)}"
        )

    return _DeviceValidationDict(_ALL_REGION_CONFIGS[region])
