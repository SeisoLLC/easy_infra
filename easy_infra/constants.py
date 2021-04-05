"""
Constants
"""

import json
from pathlib import Path

from easy_infra import __project_name__

CONFIG_FILE = Path(f"{__project_name__}.yml").absolute()
OUTPUT_FILE = Path("functions").absolute()
JINJA2_FILE = Path("functions.j2").absolute()
LOG_DEFAULT = "INFO"

IMAGE = f"seiso/{__project_name__}"
TARGETS = ["minimal", "aws", "az", "final"]

LOG_FORMAT = json.dumps(
    {
        "timestamp": "%(asctime)s",
        "namespace": "%(name)s",
        "loglevel": "%(levelname)s",
        "message": "%(message)s",
    }
)

APT_PACKAGES = {"ansible", "azure-cli"}
GITHUB_REPOS = {"tfutils/tfenv", "tfsec/tfsec"}
PYTHON_PACKAGES = {"awscli", "checkov"}
HASHICORP_PROJECTS = {"terraform", "packer"}
UNACCEPTABLE_VULNS = ["CRITICAL", "HIGH"]
INFORMATIONAL_VULNS = ["UNKNOWN", "LOW", "MEDIUM"]
