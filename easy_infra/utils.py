import sys
from logging import getLogger
from pathlib import Path
from typing import Any, Optional, Union

import docker
import requests
from jinja2 import Environment, FileSystemLoader
from yaml import YAMLError, dump, safe_load

from easy_infra import __project_name__

LOG = getLogger(__name__)
CLIENT = docker.from_env()


# Helper functions
def render_jinja2(
    *,
    template_file: Path,
    config: dict,
    output_file: Path,
    output_mode: Optional[int] = None,
) -> None:
    """Render the functions file"""
    folder = str(template_file.parent)
    file = str(template_file.name)
    LOG.info(f"Rendering {file}...")
    template = Environment(loader=FileSystemLoader(folder)).get_template(file)
    out = template.render(config)
    output_file.write_text(out)
    if output_mode is not None:
        output_file.chmod(output_mode)


def get_latest_release_from_apt(*, package: str) -> str:
    """Get the latest release of a project via apt"""
    # TODO: Reassess this
    image = "seiso/easy_infra:latest"
    CLIENT.images.pull(repository=image)
    release = CLIENT.containers.run(
        image=image,
        auto_remove=True,
        detach=False,
        user=0,
        command='/bin/bash -c "apt-get update &>/dev/null && apt-cache policy '
        + package
        + " | grep '^  Candidate:' | awk -F' ' '{print $NF}'\"",
    )
    return release


def get_latest_release_from_github(*, repo: str) -> str:
    """Get the latest release of a repo on github"""
    response = requests.get(
        f"https://api.github.com/repos/{repo}/releases/latest"
    ).json()
    return response["tag_name"]


def get_latest_tag_from_github(*, repo: str) -> str:
    """Get the latest tag of a repo on github"""
    response = requests.get(f"https://api.github.com/repos/{repo}/tags").json()
    return response[0]["name"]


def get_latest_release_from_pypi(*, package: str) -> str:
    """Get the latest release of a package on pypi"""
    response = requests.get(f"https://pypi.org/pypi/{package}/json").json()
    return response["info"]["version"]


def get_latest_release_from_hashicorp(*, project: str) -> str:
    """Get the latest release of a project from hashicorp"""
    response = requests.get(
        f"https://checkpoint-api.hashicorp.com/v1/check/{project}"
    ).json()
    return response["current_version"]


def opinionated_docker_run(
    *,
    command: str,
    image: str,
    auto_remove: bool = False,
    tty: bool = False,
    detach: bool = True,
    environment: dict = {},
    volumes: dict = {},
    working_dir: str = "/iac/",
    expected_exit: int = 0,
    network_mode: Union[str, None] = None,
):
    """Perform an opinionated docker run"""
    LOG.debug(
        "Invoking CLIENT.containers.run() with the following arguments: "
        + f"{auto_remove=}, {command=}, {detach=}, {environment=}, {image=}, {network_mode=}, {tty=}, {volumes=}, {working_dir=}"
    )
    container = CLIENT.containers.run(
        auto_remove=auto_remove,
        command=command,
        detach=detach,
        environment=environment,
        image=image,
        network_mode=network_mode,
        tty=tty,
        volumes=volumes,
        working_dir=working_dir,
    )

    if not auto_remove:
        response = container.wait(condition="not-running")
        response["logs"] = container.logs().decode("utf-8").strip().replace("\n", "  ")
        container.remove()
        if not is_status_expected(expected=expected_exit, response=response):
            sys.exit(response["StatusCode"])


def is_status_expected(*, expected: int, response: dict) -> bool:
    """Check to see if the status code was expected"""
    actual = response["StatusCode"]

    if expected != actual:
        LOG.error(
            "Received an unexpected status code of %s; additional details: %s",
            response["StatusCode"],
            response["logs"],
        )
        return False

    return True


def gather_tools_and_environments(
    *, tool: str = "all", environment: str = "all"
) -> dict[str, dict[str, list[str]]]:
    """
    Returns a dict with a key of the tool, and a value of a list of environments
    """
    from easy_infra.constants import ENVIRONMENTS, TOOLS

    if tool == "all":
        tools: Union[set[Any], list[str]] = TOOLS
    elif tool not in TOOLS:
        LOG.error(f"{tool} is not a supported tool, exiting...")
        sys.exit(1)
    else:
        tools = [tool]

    if environment == "all":
        environments = ENVIRONMENTS
    elif environment == "none":
        environments = []
    elif environment not in ENVIRONMENTS:
        LOG.error(f"{environment} is not a supported environment, exiting...")
        sys.exit(1)
    else:
        environments = [environment]

    image_and_tool_and_environment_tags = {}
    for tool in tools:
        image_and_tool_and_environment_tags[tool] = {"environments": environments}

    return image_and_tool_and_environment_tags
