import json
import sys
from logging import basicConfig, getLogger
from pathlib import Path

import docker
import git
from yaml import YAMLError, safe_load


def parse_config(*, config_file: Path) -> dict:
    """Parse the easy_infra config file"""

    # Filter
    suffix_whitelist = {".yml", ".yaml"}

    if config_file.suffix not in suffix_whitelist:
        LOG.error("Suffix for the config file %s is not allowed", config_file)
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
            "The config file %s was unable to be loaded due to the following exception: %s",
            config_file,
            str(err),
        )
        # Raise if info or debug level logging
        if LOG.getEffectiveLevel() <= 20:
            raise err
        sys.exit(1)

    return config


# Globals
CONFIG_FILE = Path("easy_infra.yml").absolute()
CONFIG = parse_config(config_file=CONFIG_FILE)
VERSION = CONFIG["version"]
CWD = Path(".").absolute()

LOG = getLogger("easy_infra")
LOG_FORMAT = json.dumps(
    {
        "timestamp": "%(asctime)s",
        "namespace": "%(name)s",
        "loglevel": "%(levelname)s",
        "message": "%(message)s",
    }
)
basicConfig(level="INFO", format=LOG_FORMAT)

# git
REPO = git.Repo(CWD)
COMMIT_HASH = REPO.head.object.hexsha

# Docker
CLIENT = docker.from_env()
IMAGE = "seiso/easy_infra"
TARGETS = {
    "minimal": {},
    "aws": {},
    "az": {},
    "final": {},
}
for target in TARGETS:
    if target == "final":
        TARGETS[target]["tags"] = [
            IMAGE + ":" + COMMIT_HASH,
            IMAGE + ":" + VERSION,
            IMAGE + ":latest",
        ]
    else:
        TARGETS[target]["tags"] = [
            IMAGE + ":" + COMMIT_HASH + "-" + target,
            IMAGE + ":" + VERSION + "-" + target,
            IMAGE + ":" + "latest" + "-" + target,
        ]
