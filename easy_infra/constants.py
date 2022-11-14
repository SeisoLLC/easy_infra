"""
easy_infra constants
"""

import copy
import json
from pathlib import Path
from typing import Union

import git
from easy_infra import __project_name__, __version__, utils

CONFIG_FILE = Path(f"{__project_name__}.yml").absolute()
CWD = Path(".").absolute()
FUNCTIONS_INPUT_FILE = CWD.joinpath("functions.j2")
FUNCTIONS_OUTPUT_FILE = CWD.joinpath(FUNCTIONS_INPUT_FILE.stem)
BUILD = CWD.joinpath("build")
DOCKERFILE_INPUT_FILE = BUILD.joinpath("Dockerfile.j2")
DOCKERFILE_OUTPUT_FILE = BUILD.joinpath("Dockerfile")

LOG_DEFAULT = "INFO"
IMAGE = f"seiso/{__project_name__}"

REPO = git.Repo(CWD)
COMMIT_HASH = REPO.head.object.hexsha
COMMIT_HASH_SHORT = REPO.git.rev_parse(COMMIT_HASH, short=True)
CONFIG = utils.parse_config(config_file=CONFIG_FILE)

# TOOLS is used to create per-tool tags. If there isn't a security configuration, the tag will not be created, because then it wouldn't fit our secure
# by default design
TOOLS = set()
for command in CONFIG["commands"]:
    if "security" in CONFIG["commands"][command]:
        TOOLS.add(command)

ENVIRONMENTS = ["aws", "azure"]

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

# TODO: Fix typing hinting
CONTEXT: dict[str, dict[str, Union[str, dict[str, Union[str, bool]]]]] = {}
CONTEXT["buildargs"] = {"COMMIT_HASH": COMMIT_HASH}
if (
    f"v{__version__}" in REPO.tags
    and REPO.tags[f"v{__version__}"].commit.hexsha == COMMIT_HASH
):
    CONTEXT["buildargs"]["EASY_INFRA_VERSION"] = __version__
    CONTEXT["buildargs"]["RELEASE"] = True
else:
    CONTEXT["buildargs"]["EASY_INFRA_VERSION"] = f"{__version__}-{COMMIT_HASH_SHORT}"
    CONTEXT["buildargs"]["RELEASE"] = False

# TODO: Build the ":latest" tag a special way; not accounted for in the TOOLS loop below
for tool in TOOLS:
    CONTEXT[tool] = {}
    # Layer the tool-specific buildargs on top of the base buildargs
    CONTEXT[tool]["buildargs"] = copy.deepcopy(CONTEXT["buildargs"])
    CONTEXT[tool]["latest_tag"] = f"latest-{tool}"

    # EASY_INFRA_TAG is a versioned tag which gets passed in at build time to populate an OCI annotation
    if CONTEXT["buildargs"]["RELEASE"]:
        CONTEXT[tool]["buildargs"]["EASY_INFRA_TAG"] = f"{__version__}-{tool}"
        CONTEXT[tool]["versioned_tag"] = f"{__version__}-{tool}"
    else:
        CONTEXT[tool]["buildargs"][
            "EASY_INFRA_TAG"
        ] = f"{__version__}-{tool}-{COMMIT_HASH_SHORT}"
        CONTEXT[tool]["versioned_tag"] = f"{__version__}-{tool}-{COMMIT_HASH_SHORT}"

    for environment in ENVIRONMENTS:
        CONTEXT[tool][environment] = {}
        CONTEXT[tool][environment]["buildargs"] = {}

        # Layer the tool-environment buildargs on top of the tool buildargs
        CONTEXT[tool][environment]["buildargs"] = copy.deepcopy(
            CONTEXT[tool]["buildargs"]
        )

        if CONTEXT["buildargs"]["RELEASE"]:
            CONTEXT[tool][environment][
                "versioned_tag"
            ] = f"{__version__}-{tool}-{environment}"
            CONTEXT[tool][environment]["latest_tag"] = f"latest-{tool}-{environment}"
            CONTEXT[tool][environment]["buildargs"][
                "EASY_INFRA_TAG"
            ] = f"{__version__}-{tool}-{environment}"
        else:
            CONTEXT[tool][environment][
                "versioned_tag"
            ] = f"{__version__}-{tool}-{environment}-{COMMIT_HASH_SHORT}"
            CONTEXT[tool][environment][
                "latest_tag"
            ] = f"latest-{tool}-{environment}-{COMMIT_HASH_SHORT}"
            CONTEXT[tool][environment]["buildargs"][
                "EASY_INFRA_TAG"
            ] = f"{__version__}-{tool}-{environment}-{COMMIT_HASH_SHORT}"
