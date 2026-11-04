"""Upgrade settings format to the latest version."""

from fiat.log import spawn_logger

logger = spawn_logger(__name__)

CURRENT_FORMAT_VERSION = 1


def upgrade_settings_v0_to_v1(data: dict) -> dict:
    """Upgrade a copy of the settings dict from version 0 to version 1."""
    logger.warning(
        "Format version 0 is deprecated and support will be dropped "
        "in a future version."
    )
    # Perform any additional migration steps for version 0 to 1 here
    return {**data, "format_version": 1}


# <format_version before upgrade>: <upgrade_function>
SUPPORTED_UPGRADES = {0: upgrade_settings_v0_to_v1}
SUPPORTED_VERSIONS = (*sorted(SUPPORTED_UPGRADES), CURRENT_FORMAT_VERSION)


def upgrade_to_latest(data: dict) -> dict:
    """Upgrade the settings dict to the latest format version."""
    version = data.get("format_version")
    if type(version) is not int or version not in SUPPORTED_VERSIONS:
        raise ValueError(
            f"Unsupported format version: {version!r}. "
            f"Supported versions: {list(SUPPORTED_VERSIONS)}."
        )
    while version != CURRENT_FORMAT_VERSION:
        data = SUPPORTED_UPGRADES[version](data)
        new_version = data.get("format_version")
        if type(new_version) is not int or new_version <= version:
            raise RuntimeError(
                f"Upgrade from format version {version} did not advance the version."
            )
        version = new_version
    return data
