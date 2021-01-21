#!/usr/bin/env python3
"""
Task execution tool & library
"""

from pathlib import Path
import sys
import json
from logging import getLogger, basicConfig
import git
from yaml import safe_load, YAMLError, dump
from jinja2 import Environment, FileSystemLoader
import requests
from invoke import task
import docker

## Helper functions
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
    image = IMAGE + ":latest-az"
    CLIENT.images.pull(repository=image)
    release = CLIENT.containers.run(
        image=image,
        auto_remove=True,
        command='/bin/bash -c "apt-get update &>/dev/null && apt-cache policy '
        + package
        + " | grep '^  Candidate:' | awk -F' ' '{print $NF}'\"",
    )
    return release


def get_latest_release_from_github(*, repo: str) -> str:
    """Get the latest release of a repo on github"""
    response = requests.get(
        "https://api.github.com/repos/" + repo + "/releases/latest"
    ).json()
    return response["tag_name"]


def get_latest_release_from_hashicorp(*, project: str) -> str:
    """Get the latest release of a project from hashicorp"""
    response = requests.get(
        "https://checkpoint-api.hashicorp.com/v1/check/" + project
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


## Globals
CONFIG_FILE = Path("easy_infra.yml").absolute()
OUTPUT_FILE = Path("functions").absolute()
JINJA2_FILE = Path("functions.j2").absolute()
CONFIG = parse_config(config_file=CONFIG_FILE)
VERSION = CONFIG["version"]
CWD = Path(".").absolute()

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
PYTHON_FILES = {"ci", "awscli", "checkov"}
HASHICORP_PROJECTS = {"terraform", "packer"}


## Tasks
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

    for python_file in PYTHON_FILES:
        image = "python:3.9"
        working_dir = "/usr/src/app/"
        volumes = {CWD: {"bind": working_dir, "mode": "rw"}}
        CLIENT.images.pull(repository=image)
        CLIENT.containers.run(
            image=image,
            volumes=volumes,
            working_dir=working_dir,
            auto_remove=True,
            command='/bin/bash -c "python3 -m pip install --upgrade pip &>/dev/null && pip3 install -r /usr/src/app/'
            + python_file
            + "-to-freeze.txt &>/dev/null && pip3 freeze > /usr/src/app/"
            + python_file
            + '.txt"',
        )


@task
def lint(c):  # pylint: disable=unused-argument
    """Lint easy_infra"""
    image = "projectatomic/dockerfile-lint"
    working_dir = "/root/"
    volumes = {CWD: {"bind": working_dir, "mode": "rw"}}
    CLIENT.images.pull(repository=image)
    CLIENT.containers.run(
        image=image,
        volumes=volumes,
        working_dir=working_dir,
        auto_remove=True,
        command="dockerfile_lint -f /root/Dockerfile -r /root/.github/workflows/etc/oci_annotations.yml",
    )


@task
def build(c):  # pylint: disable=unused-argument
    """Build easy_infra"""
    render_jinja2(template_file=JINJA2_FILE, config=CONFIG, output_file=OUTPUT_FILE)

    buildargs = {"VERSION": VERSION, "COMMIT_HASH": COMMIT_HASH}
    for thing in CONFIG["commands"]:
        if "version" in CONFIG["commands"][thing]:
            # Normalize the build args
            arg = thing.upper().replace("-", "_") + "_VERSION"
            buildargs[arg] = CONFIG["commands"][thing]["version"]

    # pylint: disable=redefined-outer-name
    for target in TARGETS:
        for tag in TARGETS[target]["tags"]:
            LOG.info("Building %s...", tag)
            CLIENT.images.build(
                path=str(CWD), target=target, rm=True, tag=tag, buildargs=buildargs
            )


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
