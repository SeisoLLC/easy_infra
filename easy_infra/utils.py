import copy
import json
import re
import sys
from logging import getLogger
from pathlib import Path
from typing import Optional, Pattern

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
    user: str = "",
    volumes: dict = {},
    working_dir: str = "/iac/",
    expected_exit: int = 0,
    check_logs: Pattern[str] | None = None,
    network_mode: str | None = None,
):
    """Perform an opinionated docker run"""
    if auto_remove and check_logs:
        LOG.error(f"auto_remove cannot be {auto_remove} when check_logs is specified")
        sys.exit(1)

    LOG.debug(
        "Invoking CLIENT.containers.run() with the following arguments: "
        + f"{auto_remove=}, {command=}, {detach=}, {environment=}, {image=}, {network_mode=}, {tty=}, {user=}, {volumes=}, {working_dir=}"
    )
    container = CLIENT.containers.run(
        auto_remove=auto_remove,
        command=command,
        detach=detach,
        environment=environment,
        image=image,
        network_mode=network_mode,
        tty=tty,
        user=user,
        volumes=volumes,
        working_dir=working_dir,
    )

    if not auto_remove:
        response = container.wait(condition="not-running")
        response["logs"] = container.logs().decode("utf-8").strip().replace("\n", "  ")
        container.remove()
        if not is_status_expected(expected=expected_exit, response=response):
            LOG.error(
                f'Received an exit code of {response["StatusCode"]} when {expected_exit} was expected '
                + "when invoking CLIENT.containers.run() with the following arguments: "
                + f"{auto_remove=}, {command=}, {detach=}, {environment=}, {image=}, {network_mode=}, {tty=}, {user=}, {volumes=}, {working_dir=}"
            )

            # This ensures that if it unexpectedly exits 0, it still fails the pipeline
            exit_code = response["StatusCode"]
            sys.exit(max(exit_code, 1))

    if check_logs and check_logs.search(response["logs"]):
        LOG.error(
            f"Found the pattern {check_logs} in the container logs; failing the test..."
        )
        sys.exit(1)


def is_status_expected(*, expected: int, response: dict) -> bool:
    """Check to see if the status code was expected"""
    actual = response["StatusCode"]

    if expected != actual:
        status_code = response["StatusCode"]
        logs = response["logs"]
        LOG.error(
            f"Received an unexpected status code of {status_code} when {expected} was expected; additional details: {logs}",
        )
        return False

    return True


def get_github_actions_matrix(*, tool: str = "all", environment: str = "all", user: str = "all", testing: bool = False) -> str:
    """Return a matrix of tool/environments or tool/environments/users for use in the github actions pipeline"""
    tools_and_environments: dict[
        str, dict[str, list[str]]
    ] = gather_tools_and_environments(tool=tool, environment=environment)
    # Unused if testing isn't true
    users: list[str] = gather_users(user=user)

    github_matrix: dict[str, list[dict[str, str]]] = {}
    github_matrix['include'] = []
    for tool, environments in tools_and_environments.items():
        job: dict[str, str] = {"tool": tool, "environment": "none"}
        if testing:
            for user in users:
                job["user"] = user
                github_matrix['include'].append(copy.copy(job))
        else:
            github_matrix['include'].append(job)
        for environment in environments["environments"]:
            job: dict[str, str] = {"tool": tool, "environment": environment}
            if testing:
                for user in users:
                    job["user"] = user
                    github_matrix['include'].append(copy.copy(job))
            else:
                github_matrix['include'].append(job)

    include: str = json.dumps(github_matrix)

    if testing:
        return f"test-matrix={include}"

    return f"image-matrix={include}"


def get_supported_environments(*, tool: str) -> list[str]:
    """Return a list of supported environments for a provided single tool"""
    if tool == "all":
        LOG.error("This function must be passed a specific tool")
        sys.exit(1)

    config = constants.CONFIG

    # We need to scan all of the packages to see if the provided tool is a custom tool name
    for package in config["packages"]:
        # First, check to see if the provided tool matches the package name
        if package == tool:
            # See if there is a custom list of environments specified
            if (
                "tool" in config["packages"][package]
                and "environments" in config["packages"][package]["tool"][tool]
            ):
                environments: list[str] = config["packages"][package]["tool"][
                    "environments"
                ]
                break

            # If there isn't a custom set of environments specified, default to all of them
            environments: list[str] = list(constants.ENVIRONMENTS)
            break

        # Second, check if the provided tool is a custom tool name
        if (
            "tool" in config["packages"][package]
            and "name" in config["packages"][package]["tool"]
        ):
            if (
                tool == config["packages"][package]["tool"]["name"]
                and "environments" in config["packages"][package]["tool"]
            ):
                environments: list[str] = config["packages"][package]["tool"][
                    "environments"
                ]
                # Remove any explicit nones, they are handled implicitly upstream
                if "none" in environments:
                    environments.remove("none")
                break

            # If there isn't a custom set of environments specified, default to all of them
            environments: list[str] = list(constants.ENVIRONMENTS)
            break
    else:
        LOG.error(f"Unable to identify the tool {tool} in the config")
        sys.exit(1)

    return environments


def gather_tools_and_environments(
    *, tool: str = "all", environment: str = "all"
) -> dict[str, dict[str, list[str]]]:
    """
    Returns a dict with a key of the tool, and a value of a list of environments
    """
    if tool == "all":
        tools: list[str] = list(constants.TOOLS)
    elif tool not in constants.TOOLS:
        LOG.error(f"{tool} is not a supported tool, exiting...")
        sys.exit(1)
    else:
        tools: list[str] = [tool]

    image_and_tool_and_environment_tags: dict[str, dict[str, list[str]]] = {}
    for tool in tools:
        if environment == "none":
            environments: list[str] = []
        elif environment == "all":
            environments: list[str] = get_supported_environments(tool=tool)
        elif environment not in constants.ENVIRONMENTS:
            LOG.error(f"{environment} is not a supported environment, exiting...")
            sys.exit(1)
        else:
            supported_environments: list[str] = get_supported_environments(tool=tool)
            if environment not in supported_environments:
                LOG.error(
                    f"{environment} is not a supported environment for {tool}, exiting..."
                )
                sys.exit(1)
            else:
                environments: list[str] = [environment]

        image_and_tool_and_environment_tags[tool] = {"environments": environments}

    return image_and_tool_and_environment_tags


def gather_users(*, user: str) -> list[str]:
    """Return a list of users, based on the simplified provided user"""
    if user == "all":
        users: list[str] = constants.USERS
    elif user not in constants.USERS:
        LOG.error(f"{user} is not a supported user, exiting...")
        sys.exit(1)
    else:
        users: list[str] = constants.USERS

    return users


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


def get_package_name(*, tool: str) -> str:
    """Return the package name for the provided tool"""
    for package in constants.CONFIG["packages"]:
        if package == tool:
            return package

        if (
            "tool" in constants.CONFIG["packages"][package]
            and "name" in constants.CONFIG["packages"][package]["tool"]
            and tool in constants.CONFIG["packages"][package]["tool"]["name"]
        ):
            return package

    LOG.error(f"Unable to find the package for tool {tool}")
    sys.exit(1)
