#!/usr/bin/env python3
"""
Task execution tool & library
"""

from pathlib import Path
import os
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
        detach=False,
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


def get_latest_release_from_pypi(*, package: str) -> str:
    """Get the latest release of a package on pypi"""
    response = requests.get("https://pypi.org/pypi/" + package + "/json").json()
    return response["info"]["version"]


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


def opinionated_docker_run(
    *,
    command: str,
    image: str,
    volumes: dict = {},
    working_dir: str = "/iac/",
    auto_remove: bool = False,
    detach: bool = True,
    environment: dict = {},
    expected_exit: int = 0,
):
    """Perform an opinionated docker run"""
    container = CLIENT.containers.run(
        auto_remove=auto_remove,
        command=command,
        detach=detach,
        environment=environment,
        image=image,
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


def test_version_commands(*, image: str, volumes: dict, working_dir: str):
    """Test the version commands listed in the config"""
    num_tests_ran = 0
    for command in CONFIG["commands"]:
        # Test the provided version commands
        if "version_command" in CONFIG["commands"][command]:
            command = "command " + CONFIG["commands"][command]["version_command"]
            opinionated_docker_run(
                image=image,
                volumes=volumes,
                working_dir=working_dir,
                command=command,
                expected_exit=0,
            )
            num_tests_ran += 1

    LOG.info("%s passed %d integration tests", image, num_tests_ran)


def run_terraform_tests(*, image: str):
    """Run the terraform tests"""
    num_tests_ran = 0
    working_dir = "/iac/"
    # Required due to the readonly volume mount
    environment = {"TF_DATA_DIR": "/tmp"}

    # Ensure invalid configurations fail
    command = "terraform plan -lock=false"
    invalid_config_dir = TESTS_PATH.joinpath("terraform/invalid")
    volumes = {invalid_config_dir: {"bind": working_dir, "mode": "ro"}}
    opinionated_docker_run(
        image=image,
        volumes=volumes,
        working_dir=working_dir,
        command=command,
        environment=environment,
        expected_exit=1,
    )
    num_tests_ran += 1

    # Ensure insecure configurations fail due to tfsec
    command = "terraform --skip-checkov --skip-terrascan plan -lock=false"
    tfsec_test_dir = TESTS_PATH.joinpath("terraform/tfsec")
    volumes = {tfsec_test_dir: {"bind": working_dir, "mode": "ro"}}
    opinionated_docker_run(
        image=image,
        volumes=volumes,
        working_dir=working_dir,
        command=command,
        environment=environment,
        expected_exit=1,
    )
    num_tests_ran += 1

    # Ensure insecure configurations fail due to checkov
    command = "terraform --skip-tfsec --skip-terrascan plan -lock=false"
    checkov_test_dir = TESTS_PATH.joinpath("terraform/checkov")
    volumes = {checkov_test_dir: {"bind": working_dir, "mode": "ro"}}
    opinionated_docker_run(
        image=image,
        volumes=volumes,
        working_dir=working_dir,
        command=command,
        environment=environment,
        expected_exit=1,
    )
    num_tests_ran += 1

    # Ensure insecure configurations fail due to terrascan
    command = "terraform --skip-tfsec --skip-checkov plan -lock=false"
    terrascan_test_dir = TESTS_PATH.joinpath("terraform/terrascan")
    volumes = {terrascan_test_dir: {"bind": working_dir, "mode": "ro"}}
    opinionated_docker_run(
        image=image,
        volumes=volumes,
        working_dir=working_dir,
        command=command,
        environment=environment,
        expected_exit=1,
    )
    num_tests_ran += 1

    # Ensure secure configurations pass
    command = "terraform plan -lock=false"
    secure_config_dir = TESTS_PATH.joinpath("terraform/secure")
    volumes = {secure_config_dir: {"bind": working_dir, "mode": "ro"}}
    opinionated_docker_run(
        image=image,
        volumes=volumes,
        working_dir=working_dir,
        command=command,
        environment=environment,
        expected_exit=0,
    )
    num_tests_ran += 1

    LOG.info("%s passed %d end to end terraform tests", image, num_tests_ran)


def run_az_stage_tests(*, image: str):
    """Run the az tests"""
    num_tests_ran = 0

    # Ensure a basic azure help command succeeds
    command = "az help"
    opinionated_docker_run(image=image, command=command, expected_exit=0)
    num_tests_ran += 1

    # Ensure a basic aws help command fails
    command = "aws help"
    opinionated_docker_run(image=image, command=command, expected_exit=127)
    num_tests_ran += 1

    LOG.info("%s passed %d integration tests", image, num_tests_ran)


def run_aws_stage_tests(*, image: str):
    """Run the aws tests"""
    num_tests_ran = 0

    # Ensure a basic aws help command succeeds
    command = "aws help"
    opinionated_docker_run(image=image, command=command, expected_exit=0)
    num_tests_ran += 1

    # Ensure a basic az help command fails
    command = "az help"
    opinionated_docker_run(image=image, command=command, expected_exit=127)
    num_tests_ran += 1

    LOG.info("%s passed %d integration tests", image, num_tests_ran)


def run_security_tests(*, image: str):
    """Run the security tests"""
    temp_dir = TESTS_PATH.joinpath("tmp")

    if os.environ.get("GITHUB_ACTIONS") == "true":
        if os.environ.get("RUNNER_TEMP"):
            # Update the temp_dir if a temporary directory is indicated by the
            # environment
            temp_dir = Path(str(os.environ.get("RUNNER_TEMP"))).absolute()
        else:
            LOG.warning(
                "Unable to determine the context due to inconsistent environment variables, falling back to %s",
                str(temp_dir),
            )

    tag = image.split(":")[-1]
    file_name = tag + ".tar"
    image_file = temp_dir.joinpath(file_name)
    raw_image = CLIENT.images.get(image).save(named=True)
    with open(image_file, "wb") as file:
        for chunk in raw_image:
            file.write(chunk)

    working_dir = "/tmp/"
    volumes = {temp_dir: {"bind": working_dir, "mode": "ro"}}

    num_tests_ran = 0
    scanner = "aquasec/trivy:latest"

    # Provide debug information about unknown, low, and medium severity
    # findings
    command = (
        "--quiet image --exit-code 0 --severity "
        + ",".join(INFORMATIONAL_VULNS)
        + " --format json --light --input "
        + working_dir
        + file_name
    )
    opinionated_docker_run(
        image=scanner, command=command, volumes=volumes, expected_exit=0
    )
    num_tests_ran += 1

    # Ensure no high or critical vulnerabilities exist in the image
    command = (
        "--quiet image --exit-code 1 --severity "
        + ",".join(UNACCEPTABLE_VULNS)
        + " --format json --light --input "
        + working_dir
        + file_name
    )
    opinionated_docker_run(
        image=scanner, command=command, volumes=volumes, expected_exit=0
    )
    num_tests_ran += 1

    LOG.info("%s passed %d security tests", image, num_tests_ran)


## Globals
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
TESTS_PATH = CWD.joinpath("tests")
UNACCEPTABLE_VULNS = ["CRITICAL", "HIGH"]
INFORMATIONAL_VULNS = ["UNKNOWN", "LOW", "MEDIUM"]


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

    for package in PYTHON_PACKAGES:
        version = get_latest_release_from_pypi(package=package)
        update_config_file(thing=package, version=version)

    # Update the CI dependencies
    image = "python:3.9"
    working_dir = "/usr/src/app/"
    volumes = {CWD: {"bind": working_dir, "mode": "rw"}}
    CLIENT.images.pull(repository=image)
    command = '/bin/bash -c "python3 -m pip install --upgrade pipenv &>/dev/null && pipenv update'
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
            run_terraform_tests(image=image)
            run_security_tests(image=image)
        elif target == "az":
            run_az_stage_tests(image=image)
            run_security_tests(image=image)
        elif target == "aws":
            run_aws_stage_tests(image=image)
            run_security_tests(image=image)
        elif target == "final":
            test_version_commands(
                image=image, volumes=default_volumes, working_dir=default_working_dir
            )
            run_terraform_tests(image=image)
            run_security_tests(image=image)
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
