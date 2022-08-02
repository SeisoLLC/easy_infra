"""
easy_infra constants
"""

import json
from pathlib import Path
from typing import Union

import git
from easy_infra import __project_name__, __version__, utils

CONFIG_FILE = Path(f"{__project_name__}.yml").absolute()
OUTPUT_FILE = Path("functions").absolute()
JINJA2_FILE = Path("functions.j2").absolute()
LOG_DEFAULT = "INFO"
IMAGE = f"seiso/{__project_name__}"
VARIANTS = ["minimal", "aws", "az", "final"]

CWD = Path(".").absolute()
REPO = git.Repo(CWD)
COMMIT_HASH = REPO.head.object.hexsha
COMMIT_HASH_SHORT = REPO.git.rev_parse(COMMIT_HASH, short=True)
CONFIG = utils.parse_config(config_file=CONFIG_FILE)

LOG_FORMAT = json.dumps(
    {
        "timestamp": "%(asctime)s",
        "namespace": "%(name)s",
        "loglevel": "%(levelname)s",
        "message": "%(message)s",
    }
)

APT_PACKAGES = {"ansible", "azure-cli"}
GITHUB_REPOS_RELEASES = {
    "checkmarx/kics",
    "env0/terratag",
    "fluent/fluent-bit",
    "hashicorp/consul-template",
    "hashicorp/envconsul",
    "tfutils/tfenv",
}
GITHUB_REPOS_TAGS = {"aws/aws-cli"}
PYTHON_PACKAGES = {"checkov"}
HASHICORP_PROJECTS = {"terraform"}

CONTEXT: dict[str, dict[str, Union[str, dict[str, str]]]] = {}

for VARIANT in VARIANTS:
    CONTEXT[VARIANT] = {}
    CONTEXT[VARIANT]["buildargs"] = {"COMMIT_HASH": COMMIT_HASH}

    # Latest tag
    if VARIANT == "final":
        CONTEXT[VARIANT]["latest_tag"] = "latest"
    else:
        CONTEXT[VARIANT]["latest_tag"] = f"latest-{VARIANT}"

    # Versioned tag
    if (
        f"v{__version__}" in REPO.tags
        and REPO.tags[f"v{__version__}"].commit.hexsha == COMMIT_HASH
    ):
        if VARIANT == "final":
            CONTEXT[VARIANT]["buildargs"] = {
                "VERSION": __version__,
            }
        else:
            CONTEXT[VARIANT]["buildargs"] = {
                "VERSION": f"{__version__}-{VARIANT}",
            }
    else:
        if VARIANT == "final":
            CONTEXT[VARIANT]["buildargs"] = {
                "VERSION": f"{__version__}-{COMMIT_HASH_SHORT}",
            }
        else:
            CONTEXT[VARIANT]["buildargs"] = {
                "VERSION": f"{__version__}-{VARIANT}-{COMMIT_HASH_SHORT}",
            }
