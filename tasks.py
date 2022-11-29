#!/usr/bin/env python3
"""
Task execution tool & library
"""

import copy
import os
import platform
import re
import shutil
import subprocess
import sys
from datetime import datetime
from logging import DEBUG, basicConfig, getLogger
from pathlib import Path
from typing import Any, Union

import docker
import requests
from bumpversion.cli import main as bumpversion
from invoke import task

from easy_infra import __project_name__, __version__, constants, utils
from tests import test as run_test

if platform.machine() == "arm64":
    PLATFORM: Union[str, None] = "linux/arm64/v8"
else:
    PLATFORM = None

LOG = getLogger(__project_name__)
CLIENT = docker.from_env()

basicConfig(level=constants.LOG_DEFAULT, format=constants.LOG_FORMAT)
# Noise suppression
getLogger("urllib3").setLevel(constants.LOG_DEFAULT)
getLogger("docker").setLevel(constants.LOG_DEFAULT)


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


def filter_config(*, config: str, tools: list[str]) -> dict:
    """Take in a configuration, filter it based on the provided tool, and return the result"""
    filtered_config = {}
    filtered_config["commands"] = {}

    for tool in tools:
        filtered_config["commands"][tool] = copy.deepcopy(config["commands"][tool])

    LOG.debug(f"Returning a filtered config of {filtered_config}")

    return filtered_config


def setup_buildargs(*, tool: str, environment: str | None = None, trace: bool) -> dict:
    """Setup the buildargs for the provided tool"""
    buildargs = {}

    if trace:
        LOG.debug("Setting trace in the buildargs...")
        buildargs["TRACE"] = "true"

    # Add the platform-based build args (imperfect)
    if platform.machine().lower() == "arm64":
        buildargs["BUILDARCH"] = "arm64"
        buildargs["KICS_ARCH"] = "arm64"
        buildargs["AWS_CLI_ARCH"] = "aarch64"
    else:
        buildargs["BUILDARCH"] = "amd64"
        buildargs["KICS_ARCH"] = "x64"
        buildargs["AWS_CLI_ARCH"] = "x86_64"

    # Add the tool version buildarg
    if "version" in constants.CONFIG["commands"][tool]:
        # Normalize and add to buildargs
        arg = tool.upper().replace("-", "_") + "_VERSION"
        buildargs[arg] = constants.CONFIG["commands"][tool]["version"]
    else:
        LOG.error(f"Unable to identify the version of {tool}")
        sys.exit(1)

    # Pull in any other buildargs that the tool cares about
    for command in constants.CONFIG["commands"]:
        if (
            # Include all commands that are referenced in the tool's security section
            command in constants.CONFIG["commands"][tool]["security"]
            # Include the versions of commands which "help" other tools
            or (
                "helper" in constants.CONFIG["commands"][command]
                and set(constants.CONFIG["commands"][command]["helper"]).intersection(
                    {tool, "all"}
                )
            )
        ):
            if "version" in constants.CONFIG["commands"][command]:
                # Normalize and add to buildargs
                arg = command.upper().replace("-", "_") + "_VERSION"
                buildargs[arg] = constants.CONFIG["commands"][command]["version"]
            else:
                LOG.error(f"Unable to identify the version of {command}")
                sys.exit(1)

    # Finally, add in buildargs for the related environment
    if environment:
        for command in constants.CONFIG["environments"][environment]["commands"]:
            if "version" in constants.CONFIG["commands"][command]:
                # Normalize and add to buildargs
                arg = command.upper().replace("-", "_") + "_VERSION"
                buildargs[arg] = constants.CONFIG["commands"][command]["version"]
            else:
                LOG.error(f"Unable to identify the version of {command}")
                sys.exit(1)

    return buildargs


def pull_image(*, image_and_tag: str, platform: str = PLATFORM) -> None:
    """Pull the provided image but continue if it fails"""
    try:
        registry_data = CLIENT.images.get_registry_data(name=f"{image_and_tag}")

        # TODO: Improve PLATFORM so it can handle Intel/amd64 systems
        if registry_data.has_platform(platform):
            LOG.info(f"Pulling {image_and_tag} (platform {platform})...")
        else:
            LOG.info(f"{image_and_tag} does not have a {platform} image available")
            return
    except docker.errors.NotFound:
        LOG.error(
            f"Unable to find {image_and_tag} registry data, not going to attempt to pull the image but continuing anyway..."
        )
        return

    try:
        CLIENT.images.pull(repository=image_and_tag, platform=platform)
    except requests.exceptions.HTTPError:
        LOG.warning(
            f"Failed to pull {image_and_tag} for platform {platform} due to an HTTP error, continuing anyway..."
        )


def log_image_build(*, build_kwargs: dict) -> None:
    """Log image build information"""
    # If we aren't running at least in debug we can just drop an info log and return
    if not LOG.isEnabledFor(DEBUG):
        LOG.info(f"Building {build_kwargs['tag']}...")
        return

    # Build out a CLI command that we can use when troubleshooting issues with the Python build process

    # Required: buildargs, dockerfile, path, platform (may be None), rm (may be False), tag, target
    # Optional: cache_from (list), pull (may be False)

    # Defaults for the optional items
    pull = False
    cache_from = ""
    for key in build_kwargs:
        match key:
            case "buildargs":
                buildargs = str()
                for arg in build_kwargs[key]:
                    buildargs += f"--build-arg {arg}={build_kwargs[key][arg]} "
            case "dockerfile":
                dockerfile = f"--file {build_kwargs['path']}/{build_kwargs[key]}"
            case "path":
                path = build_kwargs[key]
            case "platform":
                if build_kwargs[key]:
                    platform = f"--platform {build_kwargs[key]}"
                else:
                    platform = ""
            case "pull":
                if build_kwargs[key]:
                    pull = True
            case "rm":
                if build_kwargs[key]:
                    rm = "--rm"
                else:
                    rm = ""
            case "tag":
                tag = f"--tag {build_kwargs[key]}"
            case "target":
                target = f"--target {build_kwargs[key]}"
            case "cache_from":
                cache_from = str()
                for image_and_tag in build_kwargs[key]:
                    cache_from += f"--cache-from {image_and_tag} "

    if pull:
        LOG.debug(f"Running the equivalent of `docker pull {build_kwargs['tag']}`")

    LOG.debug(
        f"Running the equivalent of `docker build {rm} {buildargs} {target} {cache_from} {tag} {platform} {dockerfile} {path}`"
    )


def build_and_tag(
    *, tool: str, environment: str | None = None, trace: bool = False
) -> None:
    """Build the provided image and tag it with the provided list of tags"""
    # Input validation
    if tool not in constants.TOOLS:
        LOG.error(f"Provided an invalid tool of {tool}")
        sys.exit(1)

    if environment and environment not in constants.ENVIRONMENTS:
        LOG.error(f"Provided an invalid environment of {environment}")
        sys.exit(1)

    if environment:
        versioned_tag = constants.CONTEXT[tool][environment]["versioned_tag"]
        latest_tag = constants.CONTEXT[tool][environment]["latest_tag"]
        buildargs = copy.deepcopy(
            constants.CONTEXT[tool][environment]["buildargs_base"]
        )

        # Needed for the base of Dockerfiles for {tool}-{environment} combos
        easy_infra_tag_tool_only = constants.CONTEXT[tool]["versioned_tag"]
        buildargs["EASY_INFRA_TAG_TOOL_ONLY"] = easy_infra_tag_tool_only
    else:
        versioned_tag = constants.CONTEXT[tool]["versioned_tag"]
        latest_tag = constants.CONTEXT[tool]["latest_tag"]
        buildargs = copy.deepcopy(constants.CONTEXT[tool]["buildargs_base"])

    # Layers the setup_buildargs on top of the base buildargs from the CONTEXT
    buildargs.update(setup_buildargs(tool=tool, environment=environment, trace=trace))

    image_and_versioned_tag = f"{constants.IMAGE}:{versioned_tag}"
    tool_image_and_latest_tag_no_hash = f"{constants.IMAGE}:latest-{tool}"
    # Default; will be updated later if there are tool-env Dockerfile/frags
    tool_env_exists = False

    LOG.debug(
        f"Running build_and_tag for {image_and_versioned_tag} and {trace=} using {versioned_tag=}, {latest_tag=}, {buildargs=}"
    )

    # Build the config for rendering Dockerfile.j2
    config = {}
    config["versioned_tag"] = versioned_tag
    config["dockerfile_base"] = constants.BUILD.joinpath("Dockerfile.base").read_text(
        encoding="UTF-8"
    )

    # First, build the easy_infra_base so it doesn't attempt to look for the image in docker hub
    LOG.debug(
        f"Rendering {constants.DOCKERFILE_INPUT_FILE} to build seiso/easy_infra_base for {tool=} and {environment=}"
    )
    utils.render_jinja2(
        template_file=constants.DOCKERFILE_INPUT_FILE,
        config=config,
        output_file=constants.DOCKERFILE_OUTPUT_FILE,
    )

    base_image_and_versioned_tag = f"seiso/easy_infra_base:{versioned_tag}"
    build_kwargs = {
        "buildargs": buildargs,
        "dockerfile": "Dockerfile",
        "path": str(constants.BUILD),
        "platform": PLATFORM,
        "pull": True,
        "rm": True,
        "tag": base_image_and_versioned_tag,
        "target": "final",
    }
    log_image_build(build_kwargs=build_kwargs)
    CLIENT.images.build(**build_kwargs)

    # Required Dockerfile/frag combos
    try:
        config["dockerfile_tools"] = [
            constants.BUILD.joinpath(f"Dockerfile.{tool}").read_text(encoding="UTF-8")
        ]
        config["dockerfrag_tools"] = [
            constants.BUILD.joinpath(f"Dockerfrag.{tool}").read_text(encoding="UTF-8")
        ]
    except FileNotFoundError:
        LOG.exception(
            f"A file required to build a container containing {tool} was not found"
        )
        sys.exit(1)

    # Required Dockerfile/frag combos if the environment is set
    if environment in constants.ENVIRONMENTS:
        # Create the various config lists so they can be appended to below
        config["dockerfile_envs"] = []
        config["dockerfrag_envs"] = []
        config["dockerfile_tool_envs"] = []
        config["dockerfrag_tool_envs"] = []

        for command in constants.CONFIG["environments"][environment]["commands"]:
            try:
                config["dockerfile_envs"].append(
                    constants.BUILD.joinpath(f"Dockerfile.{command}").read_text(
                        encoding="UTF-8"
                    )
                )
                config["dockerfrag_envs"].append(
                    constants.BUILD.joinpath(f"Dockerfrag.{command}").read_text(
                        encoding="UTF-8"
                    )
                )
            except FileNotFoundError:
                LOG.exception(
                    f"An environment of {environment} was specified, but at least one of the required files for {command} was not found"
                )
                sys.exit(1)

            # Optional Dockerfiles
            if constants.BUILD.joinpath(f"Dockerfile.{tool}-{environment}").exists():
                tool_env_exists = True
                config["dockerfile_tool_envs"].append(
                    constants.BUILD.joinpath(
                        f"Dockerfile.{tool}-{environment}"
                    ).read_text(encoding="UTF-8")
                )
                try:
                    config["dockerfrag_tool_envs"].append(
                        constants.BUILD.joinpath(
                            f"Dockerfrag.{tool}-{environment}"
                        ).read_text(encoding="UTF-8")
                    )
                except FileNotFoundError:
                    LOG.exception(
                        f"Dockerfile.{tool}-{environment} existed but the related (required) Dockerfrag was not found"
                    )
                    sys.exit(1)
            else:
                LOG.debug(
                    f"No Dockerfile.{tool}-{environment} detected, skipping as it is optional..."
                )
    else:
        LOG.debug(
            "The environment was not set (or not set properly); not requiring the related Dockerfile/frag"
        )

    LOG.debug(
        f"Rendering {constants.DOCKERFILE_INPUT_FILE} to build seiso/easy_infra for {tool=} and {environment=}"
    )
    utils.render_jinja2(
        template_file=constants.DOCKERFILE_INPUT_FILE,
        config=config,
        output_file=constants.DOCKERFILE_OUTPUT_FILE,
    )

    if tool_env_exists:
        # Required so it doesn't attempt to look for the image in docker hub
        tool_image_and_versioned_tag = f"seiso/easy_infra:{easy_infra_tag_tool_only}"
        build_kwargs = {
            "buildargs": buildargs,
            "dockerfile": f"Dockerfile.{tool}",
            "path": str(constants.BUILD),
            "platform": PLATFORM,
            "rm": True,
            "tag": tool_image_and_versioned_tag,
            "target": tool,
        }
        log_image_build(build_kwargs=build_kwargs)
        CLIENT.images.build(**build_kwargs)

    try:
        # Warm up the cache
        pull_image(image_and_tag=tool_image_and_latest_tag_no_hash)

        build_kwargs = {
            "buildargs": buildargs,
            "cache_from": [tool_image_and_latest_tag_no_hash],
            "dockerfile": "Dockerfile",
            "path": str(constants.BUILD),
            "platform": PLATFORM,
            "rm": True,
            "tag": image_and_versioned_tag,
            "target": "final",
        }
        log_image_build(build_kwargs=build_kwargs)
        image_tuple = CLIENT.images.build(**build_kwargs)
        image = image_tuple[0]
    except docker.errors.BuildError as build_err:
        LOG.exception(
            f"Failed to build {image_and_versioned_tag} platform {PLATFORM}...",
        )
        log_build_log(build_err=build_err)
        sys.exit(1)

    # Tag latest
    LOG.info(f"Tagging {constants.IMAGE}:{latest_tag}...")
    image.tag(constants.IMAGE, tag=latest_tag)


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
    pull_image(image_and_tag=image)
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
        ("isort", ". --settings-file /etc/opt/goat/.isort.cfg"),
        ("black", "."),
    ]
    image = "seiso/goat:latest"
    working_dir = "/goat/"
    volumes = {constants.CWD: {"bind": working_dir, "mode": "rw"}}

    pull_image(image_and_tag=image)
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

    pull_image(image_and_tag=image)
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
def build(_c, tool="all", environment="all", trace=False, debug=False):
    """Build easy_infra"""
    if debug:
        getLogger().setLevel("DEBUG")

    tools_to_environments = utils.gather_tools_and_environments(
        tool=tool, environment=environment
    )

    # pylint: disable=redefined-argument-from-local
    for tool in tools_to_environments:
        # Render the functions that the tool cares about
        filtered_config = filter_config(config=constants.CONFIG, tools=[tool])
        utils.render_jinja2(
            template_file=constants.FUNCTIONS_INPUT_FILE,
            config=filtered_config,
            output_file=constants.FUNCTIONS_OUTPUT_FILE,
            output_mode=0o755,
        )

        # TODO: Figure out how to handle -large, somewhere in this function?

        if environment not in constants.ENVIRONMENTS:
            # Build and Tag the tool-only tag
            build_and_tag(tool=tool, trace=trace)

        # Build and Tag the tool + environment tags
        for environment in tools_to_environments[tool]["environments"]:
            build_and_tag(tool=tool, environment=environment, trace=trace)


@task
def sbom(_c, tool="all", environment="all", debug=False):
    """Generate an SBOM"""
    if debug:
        getLogger().setLevel("DEBUG")

    tools_to_environments = utils.gather_tools_and_environments(
        tool=tool, environment=environment
    )

    # pylint: disable=redefined-argument-from-local
    for tool in tools_to_environments:
        versioned_tags = []
        latest_tags = []
        image_and_versioned_tags = []
        image_and_latest_tags = []
        if not (environments := tools_to_environments[tool]["environments"]):
            versioned_tags.append(constants.CONTEXT[tool]["versioned_tag"])
            latest_tags.append(constants.CONTEXT[tool]["latest_tag"])
            image_and_versioned_tags.append(f"{constants.IMAGE}:{versioned_tag}")
            image_and_latest_tags.append(f"{constants.IMAGE}:{latest_tag}")
        else:
            for environment in environments:
                versioned_tags.append(
                    constants.CONTEXT[tool][environment]["versioned_tag"]
                )
                latest_tags.append(constants.CONTEXT[tool][environment]["latest_tag"])

            for versioned_tag in versioned_tags:
                image_and_versioned_tags.append(f"{constants.IMAGE}:{versioned_tag}")

            for latest_tag in latest_tags:
                image_and_latest_tags.append(f"{constants.IMAGE}:{latest_tag}")

        try:
            # the latest tag must be last; this interleaves the versioned and latest lists. it assumes the image and tag lists are the same length
            artifact_labels = [
                item
                for pair in zip(image_and_versioned_tags, image_and_latest_tags)
                for item in pair
            ]

            for iteration, label in enumerate(artifact_labels):
                if iteration % 2 == 1:  # True when iteration is odd
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

    # TODO: Fix
    variants = process_stages(stage=stage)

    # TODO: Replace variants with tool, security_tool, and/or environment, refactor downstream
    for variant in variants:
        # Only test using the current, versioned tag of each variant
        versioned_tag = constants.CONTEXT[variant]["buildargs"]["EASY_INFRA_VERSION"]
        image_and_tag = f"{constants.IMAGE}:{versioned_tag}"

        LOG.info(f"Testing {image_and_tag} for platform {PLATFORM}...")
        if variant == "minimal":
            run_test.run_terraform(image=image_and_tag)
            run_test.run_ansible(image=image_and_tag)
            run_test.run_security(image=image_and_tag, variant=variant)
        elif variant == "azure":
            run_test.run_azure_stage(image=image_and_tag)
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

    # TODO: Fix
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

    # TODO: Fix
    variants = process_stages(stage=stage)

    for variant in variants:
        # Always push the versioned tag (should already have a unique ID when appropriate)
        versioned_tag = constants.CONTEXT[variant]["buildargs"]["EASY_INFRA_VERSION"]
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
