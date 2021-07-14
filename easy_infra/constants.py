"""
easy_infra constants
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
GITHUB_REPOS_RELEASES = {
    "tfutils/tfenv",
    "tfsec/tfsec",
    "accurics/terrascan",
    "checkmarx/kics",
}
GITHUB_REPOS_TAGS = {"aws/aws-cli"}
PYTHON_PACKAGES = {"checkov"}
HASHICORP_PROJECTS = {"terraform", "packer"}
UNACCEPTABLE_VULNS = ["CRITICAL"]
INFORMATIONAL_VULNS = ["UNKNOWN", "LOW", "MEDIUM", "HIGH"]