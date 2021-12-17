#!/usr/bin/env python3
"""
Task execution tool & library
"""

import os
import re
import subprocess
import sys
from datetime import datetime
from logging import basicConfig, getLogger
from pathlib import Path
from typing import Union

import docker
import git
from bumpversion.cli import main as bumpversion
from easy_infra import __project_name__, __version__, constants, utils
from invoke import task
from tests import test as run_test

CWD = Path(".").absolute()
REPO = git.Repo(CWD)
COMMIT_HASH = REPO.head.object.hexsha
COMMIT_HASH_SHORT = REPO.git.rev_parse(COMMIT_HASH, short=True)
TESTS_PATH = CWD.joinpath("tests")
LOG = getLogger(__project_name__)
CLIENT = docker.from_env()
CONFIG = utils.parse_config(config_file=constants.CONFIG_FILE)

CONTEXT: dict[str, dict[str, Union[str, dict[str, str]]]] = {}

for VARIANT in constants.VARIANTS:
    CONTEXT[VARIANT] = {}
    CONTEXT[VARIANT]["buildargs"] = {"COMMIT_HASH": COMMIT_HASH}

    # Latest tag
    if VARIANT == "final":
        CONTEXT[VARIANT]["latest_tag"] = "latest"
    else:
        CONTEXT[VARIANT]["latest_tag"] = f"latest-{VARIANT}"

    # Versioned tag
    if (
        f"v{__version__}" in REPO.tags
        and REPO.tags[f"v{__version__}"].commit.hexsha == COMMIT_HASH
    ):
        if VARIANT == "final":
            CONTEXT[VARIANT]["buildargs"] = {
                "VERSION": __version__,
            }
        else:
            CONTEXT[VARIANT]["buildargs"] = {
                "VERSION": f"{__version__}-{VARIANT}",
            }
    else:
        if VARIANT == "final":
            CONTEXT[VARIANT]["buildargs"] = {
                "VERSION": f"{__version__}-{COMMIT_HASH_SHORT}",
            }
        else:
            CONTEXT[VARIANT]["buildargs"] = {
                "VERSION": f"{__version__}-{VARIANT}-{COMMIT_HASH_SHORT}",
            }

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

    LOG.info(f"Pulling {image}...")
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
    environment["INPUT_DISABLE_MYPY"] = "true"

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

    LOG.info(f"Pulling {image}...")
    CLIENT.images.pull(image)
    LOG.info(f"Running {image}...")
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

    buildargs = {}

    for command in CONFIG["commands"]:
        if "version" in CONFIG["commands"][command]:
            # Normalize the build args
            arg = command.upper().replace("-", "_") + "_VERSION"
            buildargs[arg] = CONFIG["commands"][command]["version"]

    for variant in constants.VARIANTS:
        buildargs.update(CONTEXT[variant]["buildargs"])
        versioned_tag = CONTEXT[variant]["buildargs"]["VERSION"]
        image_and_versioned_tag = f"{constants.IMAGE}:{versioned_tag}"

        LOG.info(f"Building {image_and_versioned_tag}...")
        try:
            image = CLIENT.images.build(
                path=str(CWD),
                target=variant,
                rm=True,
                tag=image_and_versioned_tag,
                buildargs=buildargs,
            )[0]
        except docker.errors.BuildError as build_err:
            LOG.exception(
                f"Failed to build {image_and_versioned_tag}, retrieving and logging the more detailed build error...",
            )
            log_build_log(build_err=build_err)
            sys.exit(1)

        latest_tag = CONTEXT[variant]["latest_tag"]
        LOG.info(f"Tagging {constants.IMAGE}:{latest_tag}...")
        image.tag(constants.IMAGE, tag=latest_tag)


@task(pre=[lint, build])
def test(_c, debug=False):
    """Test easy_infra"""
    if debug:
        getLogger().setLevel("DEBUG")

    default_working_dir = "/iac/"
    default_volumes = {TESTS_PATH: {"bind": default_working_dir, "mode": "ro"}}

    for variant in constants.VARIANTS:
        # Only test using the current, versioned tag of each variant
        versioned_tag = CONTEXT[variant]["buildargs"]["VERSION"]
        image_and_tag = f"{constants.IMAGE}:{versioned_tag}"

        LOG.info("Testing {image_and_tag}...")
        if variant == "minimal":
            run_test.run_terraform(image=image_and_tag)
            run_test.run_ansible(image=image_and_tag)
            run_test.run_security(image=image_and_tag)
        elif variant == "az":
            run_test.run_az_stage(image=image_and_tag)
            run_test.run_security(image=image_and_tag)
        elif variant == "aws":
            run_test.run_aws_stage(image=image_and_tag)
            run_test.run_security(image=image_and_tag)
        elif variant == "final":
            run_test.run_path_check(image=image_and_tag)
            run_test.version_arguments(
                image=image_and_tag,
                volumes=default_volumes,
                working_dir=default_working_dir,
            )
            run_test.run_terraform(image=image_and_tag, final=True)
            run_test.run_ansible(image=image_and_tag)
            run_test.run_cli(image=image_and_tag)
            run_test.run_security(image=image_and_tag)
        else:
            LOG.error(f"Untested stage of {variant}")


@task
def sbom(_c, debug=False):
    """Generate an SBOM"""
    if debug:
        getLogger().setLevel("DEBUG")

    for variant in constants.VARIANTS:
        versioned_tag = CONTEXT[variant]["buildargs"]["VERSION"]
        image_and_tag = f"{constants.IMAGE}:{versioned_tag}"
        docker_image_file_name = f"{variant}.tar"
        docker_image_file_path = utils.write_docker_image(
            image=image_and_tag, file_name=docker_image_file_name
        )

        try:
            if (
                f"v{__version__}" in REPO.tags
                and REPO.tags[f"v{__version__}"].commit.hexsha == COMMIT_HASH
            ):
                name = f"{variant}.v{__version__}"
            else:
                name = f"{variant}.{COMMIT_HASH_SHORT}"

            LOG.info(f"Generating sbom.{name}.spdx.json...")
            subprocess.run(
                [
                    "syft",
                    f"docker-archive:{str(docker_image_file_path)}",
                    "-o",
                    "spdx-json",
                    "--file",
                    f"sbom.{name}.spdx.json",
                ],
                capture_output=True,
                check=True,
            )
        except subprocess.CalledProcessError as error:
            LOG.error(
                f"stdout: {error.stdout.decode('utf-8')}, stderr: {error.stderr.decode('utf-8')}"
            )
            sys.exit(1)


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

    new_version = f"{date_info}.{increment}"

    bumpversion(["--new-version", new_version, "unusedpart"])


@task
def publish(_c, tag, debug=False):
    """Publish easy_infra"""
    if debug:
        getLogger().setLevel("DEBUG")

    if tag not in ["latest", "release"]:
        LOG.error("Please provide a tag of either latest or release")
        sys.exit(1)
    elif tag == "release":
        tag = __version__

    for variant in constants.VARIANTS:
        if tag == "latest":
            latest_tag = CONTEXT[variant]["latest_tag"]
            image_and_tag = f"{constants.IMAGE}:{latest_tag}"
        else:
            versioned_tag = CONTEXT[variant]["buildargs"]["VERSION"]
            image_and_tag = f"{constants.IMAGE}:{versioned_tag}"

        LOG.info(f"Pushing {image_and_tag} to docker hub...")
        CLIENT.images.push(repository=image_and_tag)

    LOG.info(f"Done publishing all of the {tag} easy_infra Docker images")


@task
def clean(_c, debug=False):
    """Clean up local easy_infra artifacts"""
    if debug:
        getLogger().setLevel("DEBUG")

    temp_dir = TESTS_PATH.joinpath("tmp")

    for tarball in temp_dir.glob("*.tar"):
        tarball.unlink()

    for sbom_files in CWD.glob("*.spdx.json"):
        sbom_files.unlink()
