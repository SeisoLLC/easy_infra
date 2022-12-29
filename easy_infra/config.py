import sys
from logging import getLogger
from pathlib import Path

from yaml import YAMLError, dump, safe_load

from easy_infra import __project_name__

LOG = getLogger(__name__)


def parse_config(*, config_file: Path) -> dict:
    """Parse the easy_infra config file"""
    # Filter
    suffix_whitelist = {".yml", ".yaml"}

    if config_file.suffix not in suffix_whitelist:
        LOG.error(f"Suffix for the config file {config_file} is not allowed")
        raise RuntimeError

    try:
        with open(config_file) as yaml_data:
            config = safe_load(yaml_data)
    except (
        YAMLError,
        FileNotFoundError,
        PermissionError,
        IsADirectoryError,
        OSError,
    ) as err:
        LOG.error(
            f"The config file {config_file} was unable to be loaded due to the following exception: {str(err)}",
        )
        # Raise if info or debug level logging
        if LOG.getEffectiveLevel() <= 20:
            raise err
        sys.exit(1)

    return config


def write_config(*, config: dict, config_file: Path):
    """Write the easy_infra config file"""
    with open(config_file, "w", encoding="utf-8") as file:
        dump(config, file)


def update_config_file(*, package: str, version: str):
    """Update the easy_infra config file"""
    # Normalize
    package = package.split("/")[-1].lower()
    if isinstance(version, bytes):
        version = version.decode("utf-8").rstrip()

    config_file = Path(f"{__project_name__}.yml").absolute()

    config = parse_config(config_file=config_file)
    allow_update = config["packages"][package].get("allow_update", True)
    current_version = config["packages"][package]["version"]

    if version == current_version:
        LOG.debug(f"No new versions have been detected for {package}")
        return

    if not allow_update:
        LOG.warning(
            f"Not updating {package} to version {version} because allow_update is set to false"
        )
        return

    config["packages"][package]["version"] = version
    LOG.info(f"Updating {package} to version {version}")
    write_config(config=config, config_file=config_file)
