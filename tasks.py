#!/usr/bin/env python3
"""
Task execution tool & library
"""

import os
import re
import sys
from datetime import datetime
from logging import basicConfig, getLogger
from pathlib import Path

import docker
import git
from bumpversion.cli import main as bumpversion
from easy_infra import __project_name__, __version__, constants, utils
from invoke import task
from tests import test as run_test

CWD = Path(".").absolute()
REPO = git.Repo(CWD)
COMMIT_HASH = REPO.head.object.hexsha
TESTS_PATH = CWD.joinpath("tests")
LOG = getLogger(__project_name__)
CLIENT = docker.from_env()
CONFIG = utils.parse_config(config_file=constants.CONFIG_FILE)

TARGETS: dict[str, dict[str, list[str]]] = {}
for target in constants.TARGETS:
    TARGETS[target] = {}
    if target == "final":
        TARGETS[target]["tags"] = [
            constants.IMAGE + ":" + __version__,
            constants.IMAGE + ":latest",
        ]
    else:
        TARGETS[target]["tags"] = [
            constants.IMAGE + ":" + __version__ + "-" + target,
            constants.IMAGE + ":" + "latest" + "-" + target,
        ]


basicConfig(level=constants.LOG_DEFAULT, format=constants.LOG_FORMAT)


def process_container(*, container: docker.models.containers.Container) -> None:
    """Process a provided container"""
    response = container.wait(condition="not-running")
    decoded_response = container.logs().decode("utf-8")
    response["logs"] = decoded_response.strip().replace("\n", "  ")
    container.remove()
    if not response["StatusCode"] == 0:
        LOG.error(
            "Received a non-zero status code from docker (%s); additional details: %s",
            response["StatusCode"],
            response["logs"],
        )
        sys.exit(response["StatusCode"])
    else:
        LOG.info("%s", response["logs"])


def log_build_log(*, build_err: docker.errors.BuildError) -> None:
    """Log the docker build log"""
    iterator = iter(build_err.build_log)
    finished = False
    while not finished:
        try:
            item = next(iterator)
            if "stream" in item:
                if item["stream"] != "\n":
                    LOG.error("%s", item["stream"].strip())
            elif "errorDetail" in item:
                LOG.error("%s", item["errorDetail"])
            else:
                LOG.error("%s", item)
        except StopIteration:
            finished = True


# Tasks
@task
def update(_c, debug=False):
    """Update the core components of easy_infra"""
    if debug:
        getLogger().setLevel("DEBUG")

    for package in constants.APT_PACKAGES:
        version = utils.get_latest_release_from_apt(package=package)
        utils.update_config_file(thing=package, version=version)

    for repo in constants.GITHUB_REPOS_RELEASES:
        version = utils.get_latest_release_from_github(repo=repo)
        utils.update_config_file(thing=repo, version=version)

    for repo in constants.GITHUB_REPOS_TAGS:
        version = utils.get_latest_tag_from_github(repo=repo)
        utils.update_config_file(thing=repo, version=version)

    for project in constants.HASHICORP_PROJECTS:
        version = utils.get_latest_release_from_hashicorp(project=project)
        utils.update_config_file(thing=project, version=version)

    for package in constants.PYTHON_PACKAGES:
        version = utils.get_latest_release_from_pypi(package=package)
        utils.update_config_file(thing=package, version=version)

    # On github they use aquasecurity but on docker hub it's aquasec, and the
    # github releases are prefaced with v but not on docker hub
    version = utils.get_latest_release_from_github(repo="aquasecurity/trivy").lstrip(
        "v"
    )
    utils.update_container_security_scanner(image="aquasec/trivy", tag=version)

    # Update the CI dependencies
    image = "python:3.9"
    working_dir = "/usr/src/app/"
    volumes = {CWD: {"bind": working_dir, "mode": "rw"}}
    CLIENT.images.pull(repository=image)
    command = '/bin/bash -c "python3 -m pip install --upgrade pipenv &>/dev/null && pipenv update"'
    utils.opinionated_docker_run(
        image=image,
        volumes=volumes,
        working_dir=working_dir,
        auto_remove=True,
        detach=False,
        command=command,
    )


@task
def reformat(_c, debug=False):
    """Reformat easy_infra"""
    if debug:
        getLogger().setLevel("DEBUG")

    entrypoint_and_command = [
        ("isort", ". --settings-file /action/lib/.automation/.isort.cfg"),
        ("black", "."),
    ]
    image = "seiso/goat:latest"
    working_dir = "/goat/"
    volumes = {CWD: {"bind": working_dir, "mode": "rw"}}

    LOG.info("Pulling %s...", image)
    CLIENT.images.pull(image)
    LOG.info("Reformatting the project...")
    for entrypoint, command in entrypoint_and_command:
        container = CLIENT.containers.run(
            auto_remove=False,
            command=command,
            detach=True,
            entrypoint=entrypoint,
            image=image,
            volumes=volumes,
            working_dir=working_dir,
        )
        process_container(container=container)


@task
def lint(_c, debug=False):
    """Lint easy_infra"""
    if debug:
        getLogger().setLevel("DEBUG")

    environment = {}
    # Default to disabling the goat built-in terrascan
    environment["INPUT_DISABLE_TERRASCAN"] = "true"

    if REPO.is_dirty(untracked_files=True):
        LOG.error("Linting requires a clean git directory to function properly")
        sys.exit(1)

    # Pass in all of the host environment variables starting with INPUT_
    for element in dict(os.environ):
        if element.startswith("INPUT_"):
            environment[element] = os.environ.get(element)

    image = "seiso/goat:latest"
    environment["RUN_LOCAL"] = True
    working_dir = "/goat/"
    volumes = {CWD: {"bind": working_dir, "mode": "rw"}}

    LOG.info("Pulling %s...", image)
    CLIENT.images.pull(image)
    LOG.info("Running %s...", image)
    container = CLIENT.containers.run(
        auto_remove=False,
        detach=True,
        environment=environment,
        image=image,
        volumes=volumes,
        working_dir=working_dir,
    )
    process_container(container=container)

    LOG.info("Linting completed successfully")


@task
def build(_c, debug=False):
    """Build easy_infra"""
    if debug:
        getLogger().setLevel("DEBUG")

    utils.render_jinja2(
        template_file=constants.JINJA2_FILE,
        config=CONFIG,
        output_file=constants.OUTPUT_FILE,
    )

    buildargs = {
        "VERSION": __version__,
        "COMMIT_HASH": COMMIT_HASH,
    }
    for command in CONFIG["commands"]:
        if "version" in CONFIG["commands"][command]:
            # Normalize the build args
            arg = command.upper().replace("-", "_") + "_VERSION"
            buildargs[arg] = CONFIG["commands"][command]["version"]

    # pylint: disable=redefined-outer-name
    for target in constants.TARGETS:
        first_image = TARGETS[target]["tags"][0]

        LOG.info("Building %s...", first_image)
        try:
            image = CLIENT.images.build(
                path=str(CWD),
                target=target,
                rm=True,
                tag=first_image,
                buildargs=buildargs,
            )[0]
        except docker.errors.BuildError as build_err:
            LOG.exception(
                "Failed to build target %s, retrieving and logging the more detailed build error...",
                target,
            )
            log_build_log(build_err=build_err)
            sys.exit(1)

        for tag in TARGETS[target]["tags"][1:]:
            LOG.info("Tagging %s...", tag)
            image.tag(constants.IMAGE, tag=tag.split(":")[-1])


@task(pre=[lint, build])
def test(_c, debug=False):
    """Test easy_infra"""
    if debug:
        getLogger().setLevel("DEBUG")

    default_working_dir = "/iac/"
    default_volumes = {TESTS_PATH: {"bind": default_working_dir, "mode": "ro"}}

    # pylint: disable=redefined-outer-name
    for target in constants.TARGETS:
        # Only test using the last tag for each target
        image = TARGETS[target]["tags"][-1]

        LOG.info("Testing %s...", image)
        if target == "minimal":
            run_test.run_terraform(image=image)
            run_test.run_ansible(image=image)
            run_test.run_security(image=image)
        elif target == "az":
            run_test.run_az_stage(image=image)
            run_test.run_security(image=image)
        elif target == "aws":
            run_test.run_aws_stage(image=image)
            run_test.run_security(image=image)
        elif target == "final":
            run_test.run_path_check(image=image)
            run_test.version_arguments(
                image=image, volumes=default_volumes, working_dir=default_working_dir
            )
            run_test.run_terraform(image=image, final=True)
            run_test.run_ansible(image=image)
            run_test.run_cli(image=image)
            run_test.run_security(image=image)
        else:
            LOG.error("Untested stage of %s", target)


@task
def release(_c, debug=False):
    """Make a new release of easy_infra"""
    if debug:
        getLogger().setLevel("DEBUG")

    if REPO.head.is_detached:
        LOG.error("In detached HEAD state, refusing to release")
        sys.exit(1)

    # Get the current date info
    date_info = datetime.now().strftime("%Y.%m")

    # Our CalVer pattern which works until year 2200, up to 100 releases a
    # month (purposefully excludes builds)
    pattern = re.compile(r"v2[0-1][0-9]{2}.(0[0-9]|1[0-2]).[0-9]{2}")

    # Identify and set the increment
    for tag in reversed(REPO.tags):
        if pattern.fullmatch(tag.name):
            latest_release = tag.name
            break
    else:
        latest_release = None

    if latest_release and date_info == latest_release[1:8]:
        increment = str(int(latest_release[9:]) + 1).zfill(2)
    else:
        increment = "01"

    new_version = date_info + "." + increment

    bumpversion(["--new-version", new_version, "unusedpart"])


@task
def publish(_c, debug=False):
    """Publish easy_infra"""
    if debug:
        getLogger().setLevel("DEBUG")

    # pylint: disable=redefined-outer-name
    for target in constants.TARGETS:
        for tag in TARGETS[target]["tags"]:
            repository = tag
            LOG.info("Pushing %s to docker hub...", repository)
            CLIENT.images.push(repository=repository)
    LOG.info("Done publishing easy_infra Docker images")


@task
def clean(_c, debug=False):
    """Clean up local easy_infra artifacts"""
    if debug:
        getLogger().setLevel("DEBUG")

    temp_dir = TESTS_PATH.joinpath("tmp")

    for tarball in temp_dir.glob("*.tar"):
        tarball.unlink()
