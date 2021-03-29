#!/usr/bin/env python3
"""
Task execution tool & library
"""

import json
import sys
from logging import basicConfig, getLogger
from pathlib import Path

import docker
import git
import requests
from invoke import task
from jinja2 import Environment, FileSystemLoader
from tests.test import (
    test_run_aws_stage,
    test_run_az_stage,
    test_run_cli,
    test_run_security,
    test_run_terraform,
    test_version_commands,
)
from yaml import YAMLError, dump, safe_load

# Helper functions
def render_jinja2(*, template_file: Path, config: dict, output_file: Path) -> None:
    """Render the functions file"""
    folder = str(template_file.parent)
    file = str(template_file.name)
    LOG.info("Rendering %s...", file)
    template = Environment(loader=FileSystemLoader(folder)).get_template(file)
    out = template.render(config)
    output_file.write_text(out)
    output_file.chmod(0o755)


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


def write_config(*, config: dict):
    """Write the easy_infra config file"""
    with open(CONFIG_FILE, "w") as file:
        dump(config, file)


def get_latest_release_from_apt(*, package: str) -> str:
    """Get the latest release of a project via apt"""
    # latest-az is used because it has the Microsoft repo added
    image = IMAGE + ":latest-az"
    CLIENT.images.pull(repository=image)
    release = CLIENT.containers.run(
        image=image,
        auto_remove=True,
        detach=False,
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


def update_config_file(*, thing: str, version: str):
    """Update the easy_infra config file"""
    # Normalize
    thing = thing.split("/")[-1].lower()
    if isinstance(version, bytes):
        version = version.decode("utf-8").rstrip()

    config = parse_config(config_file=CONFIG_FILE)
    config["commands"][thing]["version"] = version
    write_config(config=config)


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
):
    """Perform an opinionated docker run"""
    container = CLIENT.containers.run(
        auto_remove=auto_remove,
        command=command,
        detach=detach,
        environment=environment,
        image=image,
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


# Globals
CONFIG_FILE = Path("easy_infra.yml").absolute()
OUTPUT_FILE = Path("functions").absolute()
JINJA2_FILE = Path("functions.j2").absolute()
CONFIG = parse_config(config_file=CONFIG_FILE)
VERSION = CONFIG["version"]
CWD = Path(".").absolute()
TESTS_PATH = CWD.joinpath("tests")

LOG_FORMAT = json.dumps(
    {
        "timestamp": "%(asctime)s",
        "namespace": "%(name)s",
        "loglevel": "%(levelname)s",
        "message": "%(message)s",
    }
)
basicConfig(level="INFO", format=LOG_FORMAT)
LOG = getLogger("easy_infra")

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

# easy_infra
APT_PACKAGES = {"ansible", "azure-cli"}
GITHUB_REPOS = {"tfutils/tfenv", "tfsec/tfsec"}
PYTHON_PACKAGES = {"awscli", "checkov"}
HASHICORP_PROJECTS = {"terraform", "packer"}
UNACCEPTABLE_VULNS = ["CRITICAL", "HIGH"]
INFORMATIONAL_VULNS = ["UNKNOWN", "LOW", "MEDIUM"]


# Tasks
@task
def update(c):  # pylint: disable=unused-argument
    """Update the core components of easy_infra"""
    for package in APT_PACKAGES:
        version = get_latest_release_from_apt(package=package)
        update_config_file(thing=package, version=version)

    for repo in GITHUB_REPOS:
        version = get_latest_release_from_github(repo=repo)
        update_config_file(thing=repo, version=version)

    for project in HASHICORP_PROJECTS:
        version = get_latest_release_from_hashicorp(project=project)
        update_config_file(thing=project, version=version)

    for package in PYTHON_PACKAGES:
        version = get_latest_release_from_pypi(package=package)
        update_config_file(thing=package, version=version)

    # Update the CI dependencies
    image = "python:3.9"
    working_dir = "/usr/src/app/"
    volumes = {CWD: {"bind": working_dir, "mode": "rw"}}
    CLIENT.images.pull(repository=image)
    command = '/bin/bash -c "python3 -m pip install --upgrade pipenv &>/dev/null && pipenv update"'
    opinionated_docker_run(
        image=image,
        volumes=volumes,
        working_dir=working_dir,
        auto_remove=True,
        detach=False,
        command=command,
    )


@task
def lint(c):  # pylint: disable=unused-argument
    """Lint easy_infra"""
    image = "projectatomic/dockerfile-lint"
    working_dir = "/root/"
    volumes = {CWD: {"bind": working_dir, "mode": "ro"}}
    CLIENT.images.pull(repository=image)
    opinionated_docker_run(
        image=image,
        volumes=volumes,
        working_dir=working_dir,
        command="dockerfile_lint -f /root/Dockerfile -r /root/.github/workflows/etc/oci_annotations.yml",
    )


@task
def build(c):  # pylint: disable=unused-argument
    """Build easy_infra"""
    render_jinja2(template_file=JINJA2_FILE, config=CONFIG, output_file=OUTPUT_FILE)

    buildargs = {"VERSION": VERSION, "COMMIT_HASH": COMMIT_HASH}
    for command in CONFIG["commands"]:
        if "version" in CONFIG["commands"][command]:
            # Normalize the build args
            arg = command.upper().replace("-", "_") + "_VERSION"
            buildargs[arg] = CONFIG["commands"][command]["version"]

    # pylint: disable=redefined-outer-name
    for target in TARGETS:
        for tag in TARGETS[target]["tags"]:
            LOG.info("Building %s...", tag)
            CLIENT.images.build(
                path=str(CWD), target=target, rm=True, tag=tag, buildargs=buildargs
            )


@task
def test(c):  # pylint: disable=unused-argument
    """Test easy_infra"""
    default_working_dir = "/iac/"
    default_volumes = {TESTS_PATH: {"bind": default_working_dir, "mode": "ro"}}

    # pylint: disable=redefined-outer-name
    for target in TARGETS:
        # Only test using the last tag for each target
        image = TARGETS[target]["tags"][-1]

        LOG.info("Testing %s...", image)
        if target == "minimal":
            test_run_terraform(image=image)
            test_run_security(image=image)
        elif target == "az":
            test_run_az_stage(image=image)
            test_run_security(image=image)
        elif target == "aws":
            test_run_aws_stage(image=image)
            test_run_security(image=image)
        elif target == "final":
            test_version_commands(
                image=image, volumes=default_volumes, working_dir=default_working_dir
            )
            test_run_terraform(image=image)
            test_run_cli(image=image)
            test_run_security(image=image)
        else:
            LOG.error("Untested stage of %s", target)


@task
def publish(c):  # pylint: disable=unused-argument
    """Publish easy_infra"""
    # pylint: disable=redefined-outer-name
    for target in TARGETS:
        for tag in TARGETS[target]["tags"]:
            repository = tag
            LOG.info("Pushing %s to docker hub...", repository)
            CLIENT.images.push(repository=repository)
    LOG.info("Done publishing easy_infra Docker images")


@task
def clean(c):  # pylint: disable=unused-argument
    """Clean up local easy_infra artifacts"""
    temp_dir = TESTS_PATH.joinpath("tmp")

    for tarball in temp_dir.glob("*.tar"):
        tarball.unlink()
