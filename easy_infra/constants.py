"""
easy_infra constants
"""

import copy
import json
from pathlib import Path
from typing import Union

import git

from easy_infra import __project_name__, __version__, config

CWD = Path(".").absolute()
BUILD = CWD.joinpath("build")
FUNCTIONS_INPUT_FILE = BUILD.joinpath("functions.j2")
FUNCTIONS_OUTPUT_FILE = BUILD.joinpath(FUNCTIONS_INPUT_FILE.stem)
DOCKERFILE_INPUT_FILE = BUILD.joinpath("Dockerfile.j2")
DOCKERFILE_OUTPUT_FILE = BUILD.joinpath("Dockerfile")

LOG_DEFAULT = "INFO"
IMAGE = f"seiso/{__project_name__}"

REPO = git.Repo(CWD)
COMMIT_HASH = REPO.head.object.hexsha
COMMIT_HASH_SHORT = REPO.git.rev_parse(COMMIT_HASH, short=True)
CONFIG_FILE = Path(f"{__project_name__}.yml").absolute()
CONFIG = config.parse_config(config_file=CONFIG_FILE)
USERS = ["easy_infra", "root"]

# TOOLS is used to create per-tool tags. If there isn't a security configuration, the tag will not be created, because then it wouldn't fit our secure
# by default design
TOOLS = set()
for package in CONFIG["packages"]:
    if (
        "security" in CONFIG["packages"][package]
        and "helper" not in CONFIG["packages"][package]
    ):
        if (
            "tool" in CONFIG["packages"][package]
            and "name" in CONFIG["packages"][package]["tool"]
        ):
            TOOLS.add(CONFIG["packages"][package]["tool"]["name"])
        else:
            TOOLS.add(package)

ENVIRONMENTS = set()
for environment in CONFIG["environments"]:
    if "packages" in CONFIG["environments"][environment]:
        ENVIRONMENTS.add(environment)

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

CONTEXT: dict[str, dict[str, Union[str, dict[str, Union[str, bool]]]]] = {}
CONTEXT["buildargs_base"] = {"COMMIT_HASH": COMMIT_HASH}
if (
    f"v{__version__}" in REPO.tags
    and REPO.tags[f"v{__version__}"].commit.hexsha == COMMIT_HASH
):
    CONTEXT["buildargs_base"]["EASY_INFRA_VERSION"] = __version__
    RELEASE = True
else:
    CONTEXT["buildargs_base"][
        "EASY_INFRA_VERSION"
    ] = f"{__version__}-{COMMIT_HASH_SHORT}"
    RELEASE = False

# Note that there is no ":latest" tag accounted for in the TOOLS loop below
for tool in TOOLS:
    CONTEXT[tool] = {}
    # Layer the tool-specific buildargs_base on top of the base buildargs_base
    CONTEXT[tool]["buildargs_base"] = copy.deepcopy(CONTEXT["buildargs_base"])

    # EASY_INFRA_TAG is a versioned tag which gets passed in at build time to populate an OCI annotation
    if RELEASE:
        CONTEXT[tool]["buildargs_base"]["EASY_INFRA_TAG"] = f"{__version__}-{tool}"
        CONTEXT[tool]["versioned_tag"] = f"{__version__}-{tool}"
        CONTEXT[tool]["latest_tag"] = f"latest-{tool}"
    else:
        CONTEXT[tool]["buildargs_base"][
            "EASY_INFRA_TAG"
        ] = f"{__version__}-{tool}-{COMMIT_HASH_SHORT}"
        CONTEXT[tool]["versioned_tag"] = f"{__version__}-{tool}-{COMMIT_HASH_SHORT}"
        CONTEXT[tool]["latest_tag"] = f"latest-{tool}-{COMMIT_HASH_SHORT}"

    for environment in ENVIRONMENTS:
        CONTEXT[tool][environment] = {}
        CONTEXT[tool][environment]["buildargs_base"] = {}

        # Layer the tool-environment buildargs_base on top of the tool buildargs_base
        CONTEXT[tool][environment]["buildargs_base"] = copy.deepcopy(
            CONTEXT[tool]["buildargs_base"]
        )

        if RELEASE:
            CONTEXT[tool][environment][
                "versioned_tag"
            ] = f"{__version__}-{tool}-{environment}"
            CONTEXT[tool][environment]["latest_tag"] = f"latest-{tool}-{environment}"
            CONTEXT[tool][environment]["buildargs_base"][
                "EASY_INFRA_TAG"
            ] = f"{__version__}-{tool}-{environment}"
        else:
            CONTEXT[tool][environment][
                "versioned_tag"
            ] = f"{__version__}-{tool}-{environment}-{COMMIT_HASH_SHORT}"
            CONTEXT[tool][environment][
                "latest_tag"
            ] = f"latest-{tool}-{environment}-{COMMIT_HASH_SHORT}"
            CONTEXT[tool][environment]["buildargs_base"][
                "EASY_INFRA_TAG"
            ] = f"{__version__}-{tool}-{environment}-{COMMIT_HASH_SHORT}"
