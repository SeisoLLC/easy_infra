import copy
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from logging import DEBUG, basicConfig, getLogger
from pathlib import Path
from typing import Optional, Pattern

import docker
import requests
from jinja2 import Environment, FileSystemLoader

from easy_infra import __project_name__, __version__, config, constants
from tests import test as run_test

LOG = getLogger(__project_name__)
CLIENT = docker.from_env()

basicConfig(level=constants.LOG_DEFAULT, format=constants.LOG_FORMAT)
# Noise suppression
getLogger("urllib3").setLevel(constants.LOG_DEFAULT)
getLogger("docker").setLevel(constants.LOG_DEFAULT)

if os.getenv("PLATFORM"):
    PLATFORM = os.getenv("PLATFORM")
else:
    if platform.system().lower() == "darwin":
        SYSTEM = "linux"
    else:
        SYSTEM = platform.system().lower()

    PLATFORM = f"{SYSTEM}/{platform.machine()}"


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


def process_container(*, container: docker.models.containers.Container) -> None:
    """Process a provided container"""
    response = container.wait(condition="not-running")
    decoded_response = container.logs().decode("UTF-8")
    response["logs"] = decoded_response.strip().replace("\n", "  ")
    container.remove()
    status_code = response["StatusCode"]
    logs = response["logs"]
    if not status_code == 0:
        LOG.error(
            f"Received a non-zero status code from docker ({status_code}); additional details: {logs}",
        )
        sys.exit(status_code)
    else:
        LOG.info(logs)


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
    volumes: dict | list = {},
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


def get_github_actions_matrix(
    *,
    tool: str = "all",
    environment: str = "all",
    user: str = "all",
    testing: bool = False,
) -> str:
    """Return a matrix of tool/environments or tool/environments/users for use in the github actions pipeline"""
    tools_and_environments: dict[
        str, dict[str, list[str]]
    ] = gather_tools_and_environments(tool=tool, environment=environment)
    if testing:
        users: list[str] = gather_users(user=user)

    github_matrix: dict[str, list[dict[str, str]]] = {}
    github_matrix["include"] = []
    for tool, environments in tools_and_environments.items():
        job: dict[str, str] = {"tool": tool, "environment": "none"}
        if testing:
            for user in users:
                job["user"] = user
                github_matrix["include"].append(copy.copy(job))
        else:
            github_matrix["include"].append(job)
        for environment in environments["environments"]:
            job: dict[str, str] = {"tool": tool, "environment": environment}
            if testing:
                for user in users:
                    job["user"] = user
                    github_matrix["include"].append(copy.copy(job))
            else:
                github_matrix["include"].append(job)

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
        users: list[str] = [user]

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


def pull_image(*, image_and_tag: str, platform: str = PLATFORM) -> None:
    """Pull the provided image but continue if it fails"""
    try:
        registry_data = CLIENT.images.get_registry_data(name=f"{image_and_tag}")

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


def update(debug=False) -> None:
    """Update the core components of easy_infra"""
    if debug:
        getLogger().setLevel("DEBUG")

    for package in constants.APT_PACKAGES:
        version = get_latest_release_from_apt(package=package)
        config.update_config_file(package=package, version=version)

    for repo in constants.GITHUB_REPOS_RELEASES:
        version = get_latest_release_from_github(repo=repo)
        config.update_config_file(package=repo, version=version)

    for repo in constants.GITHUB_REPOS_TAGS:
        version = get_latest_tag_from_github(repo=repo)
        config.update_config_file(package=repo, version=version)

    for project in constants.HASHICORP_PROJECTS:
        version = get_latest_release_from_hashicorp(project=project)
        config.update_config_file(package=project, version=version)
        if project == "terraform":
            test_file: Path = constants.CWD.joinpath(
                "tests/terraform/hooks/secure_builtin_version/secure.tf"
            )
            update_terraform_required_version(test_file=test_file, version=version)

    for package in constants.PYTHON_PACKAGES:
        version = get_latest_release_from_pypi(package=package)
        config.update_config_file(package=package, version=version)


def filter_config(*, config: str, tools: list[str]) -> dict:
    """Take in a configuration, filter it based on the provided tool, and return the result"""
    filtered_config = {}
    filtered_config["packages"] = {}

    # Preload all of the packages with a custom "tool" name specified
    custom_tool: dict[str, str] = {}
    for package in config["packages"]:
        if (
            "tool" in config["packages"][package]
            and "name" in config["packages"][package]["tool"]
        ):
            tool: str = config["packages"][package]["tool"]["name"]
            custom_tool[tool]: str = package

    for tool in tools:
        if tool in custom_tool:
            package: str = custom_tool[tool]
            filtered_config["packages"][package] = copy.deepcopy(
                config["packages"][package]
            )
        else:
            filtered_config["packages"][tool] = copy.deepcopy(config["packages"][tool])

    LOG.debug(f"Returning a filtered config of {filtered_config}")

    return filtered_config


def add_version_to_buildarg(*, buildargs: dict, thing: str) -> str:
    """Add the version to the buildarg as a crafted key value pair"""
    # Look up the correct package
    if thing not in constants.CONFIG["packages"]:
        for package in constants.CONFIG["packages"]:
            if (
                "tool" in constants.CONFIG["packages"][package]
                and "name" in constants.CONFIG["packages"][package]["tool"]
            ):
                looked_up_package: str = package
                break
        else:
            LOG.error(
                f"Unable to find {thing} in the packages or tool names of the config"
            )
            sys.exit(1)
    else:
        # the thing provided is a package
        looked_up_package: str = thing

    # Then extract the version
    if "version" in constants.CONFIG["packages"][looked_up_package]:
        # Normalize and add to buildargs
        arg: str = looked_up_package.upper().replace("-", "_") + "_VERSION"
        buildargs[arg] = constants.CONFIG["packages"][looked_up_package]["version"]
    else:
        LOG.error(f"Unable to identify the version of {looked_up_package}")
        sys.exit(1)

    return looked_up_package


def log_build_log(*, build_err: docker.errors.BuildError) -> None:
    """Log the docker build log"""
    iterator = iter(build_err.build_log)
    finished = False
    while not finished:
        try:
            item = next(iterator)
            if "stream" in item:
                if item["stream"] != "\n":
                    single_line_item = item["stream"].strip()
                    LOG.error(single_line_item)
            elif "errorDetail" in item:
                error_detail = item["errorDetail"]
                LOG.error(error_detail)
            else:
                LOG.error(item)
        except StopIteration:
            finished = True


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


def setup_buildargs(*, tool: str, environment: str | None = None, trace: bool) -> dict:
    """Setup the buildargs for the provided tool"""
    buildargs = {}

    if trace:
        LOG.debug("Setting trace in the buildargs...")
        buildargs["TRACE"] = "true"

    # Add the platform-based build args (imperfect)
    if platform.machine().lower() == "arm64":
        buildargs["BUILDARCH"] = "arm64"
        buildargs["AWS_CLI_ARCH"] = "aarch64"
    else:
        buildargs["BUILDARCH"] = "amd64"
        buildargs["AWS_CLI_ARCH"] = "x86_64"

    # Add the tool version buildarg
    looked_up_package: str = add_version_to_buildarg(buildargs=buildargs, thing=tool)

    # Pull in any other buildargs that the tool cares about
    for package in constants.CONFIG["packages"]:
        if (
            # Include all packages that are referenced in the tool's security section
            package in constants.CONFIG["packages"][looked_up_package]["security"]
            # Include the versions of packages which "help" other tools
            or (
                "helper" in constants.CONFIG["packages"][package]
                and set(constants.CONFIG["packages"][package]["helper"]).intersection(
                    {tool, "all"}
                )
            )
        ):
            add_version_to_buildarg(buildargs=buildargs, thing=package)

    # Finally, add in buildargs for the related environment
    if environment:
        for package in constants.CONFIG["environments"][environment]["packages"]:
            add_version_to_buildarg(buildargs=buildargs, thing=package)

    return buildargs


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

    image_and_versioned_tag: str = f"{constants.IMAGE}:{versioned_tag}"
    tool_image_and_latest_tag_no_hash: str = f"{constants.IMAGE}:latest-{tool}"
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
    config["arguments"] = []

    LOG.debug(
        f"Rendering {constants.DOCKERFILE_INPUT_FILE} to build seiso/easy_infra_base for {tool=} and {environment=}"
    )
    render_jinja2(
        template_file=constants.DOCKERFILE_INPUT_FILE,
        config=config,
        output_file=constants.DOCKERFILE_OUTPUT_FILE,
    )

    base_image_and_versioned_tag = f"seiso/easy_infra_base:{versioned_tag}"

    # Purposefully has no caching
    build_kwargs = {
        "buildargs": buildargs,
        "dockerfile": "Dockerfile",
        "path": str(constants.BUILD),
        "platform": PLATFORM,
        "rm": True,
        "tag": base_image_and_versioned_tag,
        "target": "final",
    }
    log_image_build(build_kwargs=build_kwargs)
    LOG.debug(
        f"Building {base_image_and_versioned_tag} because it's probably referenced later as a FROM image"
    )
    CLIENT.images.build(**build_kwargs)

    # Required Dockerfile/frag combos
    custom_tool_name: bool = False  # Default to be updated later
    for package in constants.CONFIG["packages"]:
        # If the provided tool matches the package name, use the tool name to find the dockerfile/frag
        if package == tool:
            dockerfile_tool: str = f"Dockerfile.{tool}"
            dockerfrag_tool: str = f"Dockerfrag.{tool}"
            break

        # If the provided tool is a custom name for a tool, use the package name to find the dockerfile/frag
        if (
            "tool" in constants.CONFIG["packages"][package]
            and "name" in constants.CONFIG["packages"][package]["tool"]
        ):
            if tool == constants.CONFIG["packages"][package]["tool"]["name"]:
                custom_tool_name = True
                dockerfile_tool: str = f"Dockerfile.{package}"
                dockerfrag_tool: str = f"Dockerfrag.{package}"
                break
    else:
        LOG.error(f"Unable to identify the tool {tool} in the config")
        sys.exit(1)

    try:
        config["dockerfile_tools"] = [
            constants.BUILD.joinpath(dockerfile_tool).read_text(encoding="UTF-8")
        ]
        config["dockerfrag_tools"] = [
            constants.BUILD.joinpath(dockerfrag_tool).read_text(encoding="UTF-8")
        ]

        # populate the security tools for {tool}
        security_tools = []

        # Use the package from the earlier loop if the tool name is custom
        key = package if custom_tool_name else tool
        if "security" in constants.CONFIG["packages"][key]:
            for security_tool in constants.CONFIG["packages"][key]["security"]:
                security_tools.append(security_tool)

        # Load in the security tool dockerfiles/frags
        config["dockerfile_security_tools"] = []
        config["dockerfrag_security_tools"] = []
        for security_tool in security_tools:
            LOG.debug(
                f"Found security tool {security_tool} for {tool}, adding the related dockerfile/frag combo to the config..."
            )
            config["dockerfile_security_tools"].append(
                constants.BUILD.joinpath(f"Dockerfile.{security_tool}").read_text(
                    encoding="UTF-8"
                )
            )
            config["dockerfrag_security_tools"].append(
                constants.BUILD.joinpath(f"Dockerfrag.{security_tool}").read_text(
                    encoding="UTF-8"
                )
            )
            argument = f"{security_tool.upper()}_VERSION"
            LOG.debug(f"Adding a header argument of {argument}...")
            config["arguments"].append(argument)
    except FileNotFoundError:
        LOG.exception(f"A file required to build a {tool} container was not found")
        sys.exit(1)

    # Required Dockerfile/frag combos if the environment is set
    if environment in constants.ENVIRONMENTS:
        # Create the various config lists so they can be appended to below
        config["dockerfile_envs"] = []
        config["dockerfrag_envs"] = []
        config["dockerfile_tool_envs"] = []
        config["dockerfrag_tool_envs"] = []

        for package in constants.CONFIG["environments"][environment]["packages"]:
            try:
                config["dockerfile_envs"].append(
                    constants.BUILD.joinpath(f"Dockerfile.{package}").read_text(
                        encoding="UTF-8"
                    )
                )
                config["dockerfrag_envs"].append(
                    constants.BUILD.joinpath(f"Dockerfrag.{package}").read_text(
                        encoding="UTF-8"
                    )
                )
            except FileNotFoundError:
                LOG.exception(
                    f"An environment of {environment} was specified, but at least one of the required files for {package} was not found"
                )
                sys.exit(1)

            # Optional Dockerfiles; support tool or package named files
            if custom_tool_name:
                keys = [tool, package]
            else:
                keys = [tool]

            for key in keys:
                if constants.BUILD.joinpath(f"Dockerfile.{key}-{environment}").exists():
                    tool_env_exists = True
                    config["dockerfile_tool_envs"].append(
                        constants.BUILD.joinpath(
                            f"Dockerfile.{key}-{environment}"
                        ).read_text(encoding="UTF-8")
                    )
                    try:
                        config["dockerfrag_tool_envs"].append(
                            constants.BUILD.joinpath(
                                f"Dockerfrag.{key}-{environment}"
                            ).read_text(encoding="UTF-8")
                        )
                    except FileNotFoundError:
                        LOG.exception(
                            f"Dockerfile.{key}-{environment} existed but the related (required) Dockerfrag was not found"
                        )
                        sys.exit(1)
                else:
                    LOG.debug(
                        f"No Dockerfile.{key}-{environment} detected, skipping as it is optional..."
                    )
    else:
        LOG.debug(
            "The environment was not set (or not set properly); not requiring the related Dockerfile/frag"
        )

    LOG.debug(
        f"Rendering {constants.DOCKERFILE_INPUT_FILE} to build seiso/easy_infra for {tool=} and {environment=}"
    )
    render_jinja2(
        template_file=constants.DOCKERFILE_INPUT_FILE,
        config=config,
        output_file=constants.DOCKERFILE_OUTPUT_FILE,
    )

    if tool_env_exists:
        pull_image(image_and_tag=tool_image_and_latest_tag_no_hash)
        tool_image_and_versioned_tag: str = (
            f"seiso/easy_infra:{easy_infra_tag_tool_only}"
        )
        target = package if custom_tool_name else tool
        build_kwargs = {
            "buildargs": buildargs,
            "cache_from": [tool_image_and_latest_tag_no_hash],
            "dockerfile": dockerfile_tool,
            "path": str(constants.BUILD),
            "platform": PLATFORM,
            "rm": True,
            "tag": tool_image_and_versioned_tag,
            "target": target,
        }
        log_image_build(build_kwargs=build_kwargs)
        LOG.debug(
            f"Building {tool_image_and_versioned_tag} because it's probably referenced later as a FROM image"
        )
        CLIENT.images.build(**build_kwargs)

    try:
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
        LOG.debug(f"Building the usable image {image_and_versioned_tag}")
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
    # force=True is necessary because sometimes the latest images already exist locally because they were pulled or built as a part of being the FROM
    # of another image. force=True ensures the versioned and latest tags are pointing to the exact same container ID.
    image.tag(constants.IMAGE, tag=latest_tag, force=True)


def build(
    tool="all", environment="all", trace=False, debug=False, dry_run=False
) -> None:
    """Build easy_infra"""
    if debug:
        getLogger().setLevel("DEBUG")

    tools_to_environments = gather_tools_and_environments(
        tool=tool, environment=environment
    )

    # pylint: disable=redefined-argument-from-local
    for tool in tools_to_environments:
        tools: list[str] = [tool]
        for package in constants.CONFIG["packages"]:
            if (
                # It is a helper
                "helper" in constants.CONFIG["packages"][package]
                # And it is a helper for the tool we're working on
                and tool in constants.CONFIG["packages"][package]["helper"]
                # And it has a security config
                and "security" in constants.CONFIG["packages"][package]
            ):
                tools.append(package)
        # Render the functions that the tool cares about
        filtered_config = filter_config(config=constants.CONFIG, tools=tools)
        if not dry_run:
            render_jinja2(
                template_file=constants.FUNCTIONS_INPUT_FILE,
                config=filtered_config,
                output_file=constants.FUNCTIONS_OUTPUT_FILE,
                output_mode=0o755,
            )
        else:
            LOG.info(
                f"Would have run render_jinja2 on {constants.FUNCTIONS_INPUT_FILE}..."
            )

        if environment not in constants.ENVIRONMENTS:
            # Build and Tag the tool-only tag
            if not dry_run:
                build_and_tag(tool=tool, trace=trace)
            else:
                LOG.info(f"Would have run build_and_tag({tool=}, {trace=})")

        # Build and Tag the tool + environment tags
        for env in tools_to_environments[tool]["environments"]:
            if not dry_run:
                build_and_tag(tool=tool, environment=env, trace=trace)
            else:
                LOG.info(f"Would have run build_and_tag({tool=}, {env=}, {trace=})")


def sbom(tool="all", environment="all", debug=False) -> None:
    """Generate an SBOM"""
    if debug:
        getLogger().setLevel("DEBUG")

    tools_to_environments = gather_tools_and_environments(
        tool=tool, environment=environment
    )

    tags = get_tags(
        tools_to_environments=tools_to_environments, environment=environment
    )

    for tool in tools_to_environments:
        try:
            for iteration, tag in enumerate(tags):
                if (
                    iteration % 2 == 1
                ):  # True when iteration is odd (should be the latest tag)
                    prior_tag = tags[iteration - 1]
                    prior_file_name = f"sbom.{prior_tag}.json"
                file_name = f"sbom.{tag}.json"

                if Path(file_name).is_file() and Path(file_name).stat().st_size > 0:
                    LOG.info(f"Skipping {file_name} because it already exists...")
                    continue

                if iteration % 2 == 1:  # Again, latest tag
                    LOG.info(
                        f"Copying {prior_file_name} into {file_name} since they are the same..."
                    )
                    shutil.copy(prior_file_name, file_name)
                    continue

                image_and_tag = f"{constants.IMAGE}:{tag}"
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
                f"stdout: {error.stdout.decode('UTF-8')}, stderr: {error.stderr.decode('UTF-8')}"
            )
            sys.exit(1)


def test(tool="all", environment="all", user="all", debug=False) -> None:
    """Test easy_infra"""
    if debug:
        getLogger().setLevel("DEBUG")

    tools_to_environments = gather_tools_and_environments(
        tool=tool, environment=environment
    )
    users: list[str] = gather_users(user=user)

    tags: list[str] = get_tags(
        tools_to_environments=tools_to_environments,
        environment=environment,
        only_versioned=True,
    )

    image_and_versioned_tags: list[str] = []

    # pylint: disable=redefined-argument-from-local
    for tag in tags:
        image_and_versioned_tags.append(f"{constants.IMAGE}:{tag}")

    # Only test using the versioned tag
    for image_and_versioned_tag in image_and_versioned_tags:
        for user in users:
            LOG.info(
                f"Testing {image_and_versioned_tag} for platform {PLATFORM} with user {user}..."
            )
            run_test.run_tests(
                image=image_and_versioned_tag,
                tool=tool,
                environment=environment,
                user=user,
            )

            # Cleanup after test runs
            try:
                subprocess.run(
                    ["find", ".", "-ls"],
                    capture_output=True,
                    check=True,
                )
            except subprocess.CalledProcessError as error:
                LOG.error(
                    f"stdout: {error.stdout.decode('UTF-8')}, stderr: {error.stderr.decode('UTF-8')}"
                )
                sys.exit(1)


def vulnscan(tool="all", environment="all", debug=False) -> None:
    """Scan easy_infra for vulns"""
    if debug:
        getLogger().setLevel("DEBUG")

    tools_to_environments = gather_tools_and_environments(
        tool=tool, environment=environment
    )

    tags = get_tags(
        tools_to_environments=tools_to_environments, environment=environment
    )

    for tag in tags:
        run_test.run_security(tag=tag)


def publish(tool="all", environment="all", debug=False, dry_run=False) -> None:
    """Publish easy_infra"""
    if debug:
        getLogger().setLevel("DEBUG")

    tools_to_environments = gather_tools_and_environments(
        tool=tool, environment=environment
    )

    tags = get_tags(
        tools_to_environments=tools_to_environments, environment=environment
    )

    # pylint: disable=redefined-argument-from-local
    for tag in tags:
        image_and_tag = f"{constants.IMAGE}:{tag}"
        if dry_run:
            LOG.info(f"Would have run CLIENT.images.push(repository={image_and_tag}")
        else:
            LOG.info(f"Pushing {image_and_tag} to docker hub...")
            CLIENT.images.push(repository=image_and_tag)

    LOG.info("Done publishing the easy_infra Docker images")


def tag(push=False, debug=False) -> None:
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
