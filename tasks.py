#!/usr/bin/env python3
"""
Task execution tool & library
"""

import os
import platform
import re
import shutil
import subprocess
import sys
from datetime import datetime
from logging import basicConfig, getLogger
from pathlib import Path
from typing import Union

import docker
from bumpversion.cli import main as bumpversion
from easy_infra import __project_name__, __version__, constants, utils
from invoke import task
from tests import test as run_test

if platform.machine() == "arm64":
    PLATFORM: Union[str, None] = "linux/arm64/v8"
else:
    PLATFORM = None

LOG = getLogger(__project_name__)
CLIENT = docker.from_env()

basicConfig(level=constants.LOG_DEFAULT, format=constants.LOG_FORMAT)
getLogger("urllib3").setLevel(constants.LOG_DEFAULT)


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


def process_stages(*, stage: str) -> list[str]:
    """Process the provided stage"""
    if stage == "all":
        stages = constants.VARIANTS
    elif stage not in constants.VARIANTS:
        LOG.error(f"{stage} is not a known variant, exiting...")
        sys.exit(1)
    else:
        stages = [stage]

    return stages


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

    # Update the CI dependencies
    image = "python:3.10"
    working_dir = "/usr/src/app/"
    volumes = {constants.CWD: {"bind": working_dir, "mode": "rw"}}
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
    volumes = {constants.CWD: {"bind": working_dir, "mode": "rw"}}

    LOG.info(f"Pulling {image} (platform {PLATFORM})...")
    CLIENT.images.pull(repository=image, platform=PLATFORM)
    LOG.info("Reformatting the project...")
    for entrypoint, command in entrypoint_and_command:
        container = CLIENT.containers.run(
            auto_remove=False,
            command=command,
            detach=True,
            entrypoint=entrypoint,
            image=image,
            platform=PLATFORM,
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

    if constants.REPO.is_dirty(untracked_files=True):
        LOG.error("Linting requires a clean git directory to function properly")
        sys.exit(1)

    # Pass in all of the host environment variables starting with INPUT_
    for element in dict(os.environ):
        if element.startswith("INPUT_"):
            environment[element] = os.environ.get(element)

    image = "seiso/goat:latest"
    environment["RUN_LOCAL"] = True
    working_dir = "/goat/"
    volumes = {constants.CWD: {"bind": working_dir, "mode": "rw"}}

    LOG.info(f"Pulling {image}...")
    CLIENT.images.pull(repository=image, platform=PLATFORM)
    LOG.info(f"Running {image}...")
    container = CLIENT.containers.run(
        auto_remove=False,
        detach=True,
        environment=environment,
        image=image,
        platform=PLATFORM,
        volumes=volumes,
        working_dir=working_dir,
    )
    process_container(container=container)

    LOG.info("Linting completed successfully")


@task
def build(_c, stage="all", debug=False):
    """Build easy_infra"""
    if debug:
        getLogger().setLevel("DEBUG")

    utils.render_jinja2(
        template_file=constants.JINJA2_FILE,
        config=constants.CONFIG,
        output_file=constants.OUTPUT_FILE,
    )

    buildargs = {}

    # Standard args
    buildargs["BUILDARCH"] = platform.machine().lower()

    # Customizations for certain build artifacts
    if platform.machine().lower() == "arm64":
        buildargs["KICS_ARCH"] = "arm64"
        buildargs["AWS_CLI_ARCH"] = "aarch64"
    else:
        buildargs["KICS_ARCH"] = "x64"
        buildargs["AWS_CLI_ARCH"] = "x86_64"

    for command in constants.CONFIG["commands"]:
        if "version" in constants.CONFIG["commands"][command]:
            # Normalize the build args
            arg = command.upper().replace("-", "_") + "_VERSION"
            buildargs[arg] = constants.CONFIG["commands"][command]["version"]

    variants = process_stages(stage=stage)

    for variant in variants:
        # This pulls the appropriate latest image from Docker Hub to be used as a cache when building
        latest_tag = constants.CONTEXT[variant]["latest_tag"]
        image_and_latest_tag = f"{constants.IMAGE}:{latest_tag}"
        LOG.info(f"Pulling {image_and_latest_tag}...")
        CLIENT.images.pull(image_and_latest_tag)

        buildargs.update(constants.CONTEXT[variant]["buildargs"])
        versioned_tag = constants.CONTEXT[variant]["buildargs"]["VERSION"]
        image_and_versioned_tag = f"{constants.IMAGE}:{versioned_tag}"

        LOG.info(f"Building {image_and_versioned_tag} (platform {PLATFORM}...")

        try:
            image = CLIENT.images.build(
                path=str(constants.CWD),
                target=variant,
                rm=True,
                tag=image_and_versioned_tag,
                platform=PLATFORM,
                buildargs=buildargs,
                cache_from=[image_and_latest_tag],
            )[0]
        except docker.errors.BuildError as build_err:
            LOG.exception(
                f"Failed to build {image_and_versioned_tag} for platform {PLATFORM}, retrieving and logging the more detailed build error...",
            )
            log_build_log(build_err=build_err)
            sys.exit(1)

        LOG.info(f"Tagging {constants.IMAGE}:{latest_tag} (platform {PLATFORM})...")
        image.tag(constants.IMAGE, tag=latest_tag)


@task
def sbom(_c, stage="all", debug=False):
    """Generate an SBOM"""
    if debug:
        getLogger().setLevel("DEBUG")

    variants = process_stages(stage=stage)

    for variant in variants:
        latest_tag = constants.CONTEXT[variant]["buildargs"]["VERSION"]
        image_and_tag = f"{constants.IMAGE}:{latest_tag}"

        try:
            artifact_labels = utils.get_artifact_labels(variant=variant)

            for iteration, label in enumerate(artifact_labels):
                if iteration > 0:
                    prior_label = artifact_labels[iteration - 1]
                    prior_file_name = f"sbom.{prior_label}.json"
                file_name = f"sbom.{label}.json"

                if Path(file_name).is_file() and Path(file_name).stat().st_size > 0:
                    LOG.info(f"Skipping {file_name} because it already exists...")
                    continue

                if iteration > 0:
                    LOG.info(
                        f"Copying {prior_file_name} into {file_name} since they are the same..."
                    )
                    shutil.copy(prior_file_name, file_name)
                    continue

                LOG.info(f"Generating {file_name} from {image_and_tag}...")
                subprocess.run(
                    [
                        "syft",
                        f"docker:{image_and_tag}",
                        "-o",
                        "json",
                        "--file",
                        file_name,
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
def test(_c, stage="all", debug=False):
    """Test easy_infra"""
    if debug:
        getLogger().setLevel("DEBUG")

    default_working_dir = "/iac/"
    tests_path = constants.CWD.joinpath("tests")
    default_volumes = {tests_path: {"bind": default_working_dir, "mode": "ro"}}

    variants = process_stages(stage=stage)

    for variant in variants:
        # Only test using the current, versioned tag of each variant
        versioned_tag = constants.CONTEXT[variant]["buildargs"]["VERSION"]
        image_and_tag = f"{constants.IMAGE}:{versioned_tag}"

        LOG.info(f"Testing {image_and_tag} for platform {PLATFORM}...")
        if variant == "minimal":
            run_test.run_terraform(image=image_and_tag)
            run_test.run_ansible(image=image_and_tag)
            run_test.run_security(image=image_and_tag, variant=variant)
        elif variant == "az":
            run_test.run_az_stage(image=image_and_tag)
            run_test.run_terraform(image=image_and_tag)
            run_test.run_ansible(image=image_and_tag)
            run_test.run_security(image=image_and_tag, variant=variant)
        elif variant == "aws":
            run_test.run_aws_stage(image=image_and_tag)
            run_test.run_terraform(image=image_and_tag)
            run_test.run_ansible(image=image_and_tag)
            run_test.run_security(image=image_and_tag, variant=variant)
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
            run_test.run_security(image=image_and_tag, variant=variant)
        else:
            LOG.error(f"Untested stage of {variant}")


@task
def vulnscan(_c, stage="all", debug=False):
    """Scan easy_infra for vulns"""
    if debug:
        getLogger().setLevel("DEBUG")

    variants = process_stages(stage=stage)

    for variant in variants:
        latest_tag = constants.CONTEXT[variant]["latest_tag"]
        image_and_tag = f"{constants.IMAGE}:{latest_tag}"

        LOG.debug(
            f"Running run_test.run_security(image={image_and_tag}, variant={variant})..."
        )
        run_test.run_security(image=image_and_tag, variant=variant)


@task
def release(_c, debug=False):
    """Make a new release of easy_infra"""
    if debug:
        getLogger().setLevel("DEBUG")

    if constants.REPO.head.is_detached:
        LOG.error("In detached HEAD state, refusing to release")
        sys.exit(1)

    # Get the current date info
    date_info = datetime.now().strftime("%Y.%m")

    pattern = re.compile(r"v2[0-1][0-9]{2}.(0[0-9]|1[0-2]).[0-9]{2}")

    # Identify and set the increment
    for tag in reversed(constants.REPO.tags):
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
def publish(_c, tag, stage="all", debug=False):
    """Publish easy_infra"""
    if debug:
        getLogger().setLevel("DEBUG")

    if tag not in ["main", "release"]:
        LOG.error("Please provide a tag of either main or release")
        sys.exit(1)
    elif tag == "release":
        tag = __version__

    variants = process_stages(stage=stage)

    for variant in variants:
        # Always push the versioned tag (should already have a unique ID when appropriate)
        versioned_tag = constants.CONTEXT[variant]["buildargs"]["VERSION"]
        image_and_tags = [f"{constants.IMAGE}:{versioned_tag}"]

        # Add the latest tag for merges into main
        if tag == "main":
            latest_tag = constants.CONTEXT[variant]["latest_tag"]
            image_and_tags.append(f"{constants.IMAGE}:{latest_tag}")

        for image_and_tag in image_and_tags:
            LOG.info(f"Pushing {image_and_tag} to docker hub...")
            CLIENT.images.push(repository=image_and_tag)

    LOG.info(
        f"Done publishing all of the {tag} easy_infra Docker images for platform {PLATFORM}"
    )


@task
def clean(_c, debug=False):
    """Clean up local easy_infra artifacts"""
    if debug:
        getLogger().setLevel("DEBUG")

    cleanup_list = []
    # OS files
    cleanup_list.extend(list(constants.CWD.glob("**/.DS_Store")))
    cleanup_list.extend(list(constants.CWD.glob("**/.Thumbs.db")))

    # Terraform files
    cleanup_list.extend(list(constants.CWD.glob("**/.terraform")))

    # Python files
    cleanup_list.extend(list(constants.CWD.glob("**/*.mypy_cache")))
    cleanup_list.extend(list(constants.CWD.glob("**/*.pyc")))
    cleanup_list.extend(list(constants.CWD.glob("**/__pycache__")))

    # easy_infra specific files
    cleanup_list.extend(list(constants.CWD.glob("sbom.*.json")))
    cleanup_list.extend(list(constants.CWD.glob("vulns.*.json")))

    for item in cleanup_list:
        if item.is_dir():
            shutil.rmtree(item)
        elif item.is_file():
            item.unlink()


@task
def tag(_c, push=False, debug=False):
    """Tag a release commit"""
    if debug:
        getLogger().setLevel("DEBUG")

    if constants.REPO.is_dirty(untracked_files=True):
        LOG.error("Tagging a release requires a clean git directory to avoid confusion")
        sys.exit(1)

    version_tag = f"v{__version__}"
    head_commit_message = constants.REPO.head.commit.message
    remote = constants.REPO.remote()

    if not head_commit_message.startswith("Bump version: "):
        LOG.warning(
            "HEAD does not appear to be a release; pulling the remote main branch..."
        )
        remote.pull("main")
        LOG.debug("Completed a git pull")
        head_commit_message = constants.REPO.head.commit.message

        if not head_commit_message.startswith("Bump version: "):
            LOG.error("HEAD still does not appear to be a release")
            sys.exit(1)

    LOG.info(f"Tagging the local repo with {version_tag}...")
    constants.REPO.create_tag(version_tag, message=head_commit_message)

    if push:
        LOG.info(f"Pushing the {version_tag} tag to GitHub...")
        remote.push(version_tag)
