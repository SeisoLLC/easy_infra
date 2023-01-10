import re
import sys
from logging import getLogger
from pathlib import Path
from typing import Any, Optional, Pattern, Union

import docker
import requests
from jinja2 import Environment, FileSystemLoader

from easy_infra import constants

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
    # Needs to be an image with all the apt sources
    image = "seiso/easy_infra:latest-terraform-azure"
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
            LOG.error(
                "Received an unexpected exit when invoking CLIENT.containers.run() with the following arguments: "
                + f"{auto_remove=}, {command=}, {detach=}, {environment=}, {image=}, {network_mode=}, {tty=}, {volumes=}, {working_dir=}"
            )

            # This ensures that if it unexpectedly exits 0, it still fails the pipeline
            exit_code = response["StatusCode"]
            sys.exit(max(exit_code, 1))


def is_status_expected(*, expected: int, response: dict) -> bool:
    """Check to see if the status code was expected"""
    actual = response["StatusCode"]

    if expected != actual:
        status_code = response["StatusCode"]
        logs = response["logs"]
        LOG.error(
            f"Received an unexpected status code of {status_code}; additional details: {logs}",
        )
        return False

    return True


def gather_tools_and_environments(
    *, tool: str = "all", environment: str = "all"
) -> dict[str, dict[str, list[str]]]:
    """
    Returns a dict with a key of the tool, and a value of a list of environments
    """
    if tool == "all":
        tools: Union[set[Any], list[str]] = constants.TOOLS
    elif tool not in constants.TOOLS:
        LOG.error(f"{tool} is not a supported tool, exiting...")
        sys.exit(1)
    else:
        tools = [tool]

    if environment == "all":
        environments = constants.ENVIRONMENTS
    elif environment == "none":
        environments = []
    elif environment not in constants.ENVIRONMENTS:
        LOG.error(f"{environment} is not a supported environment, exiting...")
        sys.exit(1)
    else:
        environments = [environment]

    image_and_tool_and_environment_tags = {}
    for tool in tools:
        image_and_tool_and_environment_tags[tool] = {"environments": environments}

    return image_and_tool_and_environment_tags


def get_image_and_tag(*, tool: str, environment: str | None = None) -> str:
    """Return the image_and_tag for the given tool and environment"""
    if environment and environment in constants.ENVIRONMENTS:
        tag = constants.CONTEXT[tool][environment]["versioned_tag"]
    else:
        tag = constants.CONTEXT[tool]["versioned_tag"]

    image_and_tag = f"{constants.IMAGE}:{tag}"

    return image_and_tag


def get_tags(
    *, tools_to_environments: dict, environment: str, only_versioned: bool = False
) -> list[str]:
    """
    Return an alternating list of the versioned and latest tags
    """
    versioned_tags = []
    latest_tags = []
    for tool in tools_to_environments:
        # Add the tool-only tags only when a single environment isn't provided
        if environment not in constants.ENVIRONMENTS:
            versioned_tags.append(constants.CONTEXT[tool]["versioned_tag"])
            latest_tags.append(constants.CONTEXT[tool]["latest_tag"])

        if environments := tools_to_environments[tool]["environments"]:
            for env in environments:
                versioned_tags.append(constants.CONTEXT[tool][env]["versioned_tag"])
                latest_tags.append(constants.CONTEXT[tool][env]["latest_tag"])

    tags = [item for pair in zip(versioned_tags, latest_tags) for item in pair]

    if only_versioned:
        tags = tags[::2]

    return tags


def update_terraform_required_version(*, test_file: Path, version: str) -> None:
    """Update the terraform required_version in the tests"""
    pattern: Pattern[str] = re.compile(r'^([ \t]+)required_version = "[\d.]+"$\n')
    final_content: list[str] = []

    # Validate
    if not test_file.is_file():
        LOG.error(f"{test_file} is not a valid file")
        sys.exit(1)

    # Read lines of the provided file into a list
    with test_file.open(encoding="utf-8") as file:
        file_contents: list[str] = file.readlines()

    # Transform the list to update the required_version line
    for line in file_contents:
        if match := pattern.fullmatch(line):
            # The first grouping is the whitespace
            whitespace = match.group(1)
            new_line: str = f'{whitespace}required_version = "{version}"\n'
            final_content.append(new_line)
            continue

        final_content.append(line)

    # Load
    with test_file.open("w", encoding="utf-8") as file:
        file.writelines(final_content)
