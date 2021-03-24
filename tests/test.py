import json
import os
import sys
from logging import basicConfig, getLogger
from pathlib import Path

import docker
import git
import tests.constants as constants
from yaml import YAMLError, safe_load

# Globals
OUTPUT_FILE = Path("functions").absolute()
JINJA2_FILE = Path("functions.j2").absolute()
CWD = Path(".").absolute()
TESTS_PATH = CWD.joinpath("tests")
LOG = getLogger("easy_infra")


# easy_infra
APT_PACKAGES = {"ansible", "azure-cli"}
GITHUB_REPOS = {"tfutils/tfenv", "tfsec/tfsec"}
PYTHON_PACKAGES = {"awscli", "checkov"}
HASHICORP_PROJECTS = {"terraform", "packer"}
TESTS_PATH = CWD.joinpath("tests")
UNACCEPTABLE_VULNS = ["CRITICAL", "HIGH"]
INFORMATIONAL_VULNS = ["UNKNOWN", "LOW", "MEDIUM"]


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
    container = constants.CLIENT.containers.run(
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


def version_commands(*, image: str, volumes: dict, working_dir: str):
    """Test the version commands listed in the config"""
    num_tests_ran = 0
    for command in constants.CONFIG["commands"]:
        # Test the provided version commands
        if "version_command" in constants.CONFIG["commands"][command]:
            command = (
                "command " + constants.CONFIG["commands"][command]["version_command"]
            )
            opinionated_docker_run(
                image=image,
                volumes=volumes,
                working_dir=working_dir,
                command=command,
                expected_exit=0,
            )
            num_tests_ran += 1

    LOG.info("%s passed %d integration tests", image, num_tests_ran)


def exec_terraform(
    *,
    tests: list[tuple[dict, str, int]],
    volumes: dict,
    image: str,
) -> int:
    """Execute the provided terraform tests and return a count of tests run"""
    num_tests_ran = 0
    config_dir = list(volumes.keys())[0]
    working_dir = volumes[config_dir]["bind"]

    for environment, command, expected_exit in tests:
        LOG.debug(
            '{"environment": %s, "command": "%s", "expected_exit": %s}',
            environment,
            command,
            expected_exit,
        )
        opinionated_docker_run(
            command=command,
            environment=environment,
            expected_exit=expected_exit,
            image=image,
            volumes=volumes,
            working_dir=working_dir,
        )
        num_tests_ran += 1
    return num_tests_ran


def run_terraform(*, image: str):
    """Run the terraform tests"""
    num_tests_ran = 0
    working_dir = "/iac/"
    environment = {"TF_DATA_DIR": "/tmp"}
    invalid_test_dir = TESTS_PATH.joinpath("terraform/invalid")
    invalid_volumes = {invalid_test_dir: {"bind": working_dir, "mode": "rw"}}
    tfsec_test_dir = TESTS_PATH.joinpath("terraform/tfsec")
    tfsec_volumes = {tfsec_test_dir: {"bind": working_dir, "mode": "rw"}}
    checkov_test_dir = TESTS_PATH.joinpath("terraform/checkov")
    checkov_volumes = {checkov_test_dir: {"bind": working_dir, "mode": "rw"}}
    terrascan_test_dir = TESTS_PATH.joinpath("terraform/terrascan")
    terrascan_volumes = {terrascan_test_dir: {"bind": working_dir, "mode": "rw"}}
    secure_config_dir = TESTS_PATH.joinpath("terraform/secure")
    secure_volumes = {secure_config_dir: {"bind": working_dir, "mode": "rw"}}

    # Ensure invalid configurations fail
    command = "terraform plan"
    opinionated_docker_run(
        image=image,
        volumes=invalid_volumes,
        command=command,
        environment=environment,
        expected_exit=1,
    )
    num_tests_ran += 1

    # Ensure insecure configurations fail due to tfsec
    # Tests is a list of tuples containing the test environment, command, and
    # expected exit code
    tests: list[tuple[dict, str, int]] = [
        ({}, "terraform --skip-checkov --skip-terrascan plan", 1),
        (
            {},
            "SKIP_CHECKOV=true SKIP_TERRASCAN=true terraform plan",
            127,
        ),  # Not supported; prepended variables do not work unless the
        #     commands are passed through bash
        (
            {},
            '/usr/bin/env bash -c "SKIP_CHECKOV=true SKIP_TERRASCAN=true terraform plan"',
            1,
        ),
        (
            {"SKIP_CHECKOV": "true"},
            '/usr/bin/env bash -c "SKIP_TERRASCAN=true terraform plan || true"',
            0,
        ),
        (
            {"SKIP_CHECKOV": "true"},
            '/usr/bin/env bash -c "SKIP_TERRASCAN=true terraform plan || true && false"',
            1,
        ),
        (
            {"SKIP_CHECKOV": "true"},
            '/usr/bin/env bash -c "SKIP_TERRASCAN=true terraform plan || false"',
            1,
        ),
        ({"SKIP_CHECKOV": "true"}, "terraform --skip-terrascan plan", 1),
        ({"SKIP_TERRASCAN": "TRUE"}, "terraform --skip-checkov plan", 1),
        ({"SKIP_TERRASCAN": "True", "SKIP_CHECKOV": "TrUe"}, "terraform plan", 1),
        (
            {"SKIP_TERRASCAN": "tRuE", "SKIP_CHECKOV": "FaLsE"},
            "terraform --skip-checkov plan --skip-terrascan",
            1,
        ),
        (
            {"SKIP_TERRASCAN": "tRuE", "SKIP_TFSEC": "false"},
            "terraform --skip-checkov plan --skip-terrascan",
            1,
        ),
        (
            {},
            '/usr/bin/env bash -c "terraform --skip-checkov --skip-terrascan plan || true"',
            0,
        ),
    ]

    num_tests_ran += exec_terraform(tests=tests, volumes=tfsec_volumes, image=image)

    # Ensure insecure configurations fail due to checkov
    # Tests is a list of tuples containing the test environment, command, and
    # expected exit code
    tests: list[tuple[dict, str, int]] = [
        ({}, "terraform --skip-tfsec --skip-terrascan plan", 1),
        (
            {},
            '/usr/bin/env bash -c "SKIP_TFSEC=true SKIP_TERRASCAN=true terraform plan"',
            1,
        ),
        (
            {"SKIP_TFSEC": "true"},
            '/usr/bin/env bash -c "SKIP_TERRASCAN=true terraform plan || true"',
            0,
        ),
        (
            {"SKIP_TFSEC": "true"},
            '/usr/bin/env bash -c "SKIP_TERRASCAN=true terraform plan || true && false"',
            1,
        ),
        (
            {"SKIP_TFSEC": "true"},
            '/usr/bin/env bash -c "SKIP_TERRASCAN=true terraform plan || false"',
            1,
        ),
        ({"SKIP_TFSEC": "true"}, "terraform plan --skip-terrascan", 1),
        ({"SKIP_TERRASCAN": "true"}, "terraform --skip-tfsec plan", 1),
        ({"SKIP_TFSEC": "true"}, "terraform --skip-tfsec plan --skip-terrascan", 1),
        (
            {"SKIP_TERRASCAN": "true", "SKIP_TFSEC": "true"},
            "terraform --skip-tfsec plan --skip-terrascan",
            1,
        ),
    ]

    num_tests_ran += exec_terraform(tests=tests, volumes=checkov_volumes, image=image)

    # Ensure insecure configurations fail due to terrascan
    # Tests is a list of tuples containing the test environment, command, and
    # expected exit code
    tests: list[tuple[dict, str, int]] = [
        ({}, "terraform --skip-tfsec --skip-checkov plan", 3),
        (
            {},
            '/usr/bin/env bash -c "SKIP_TFSEC=true SKIP_CHECKOV=true terraform plan"',
            3,
        ),
        (
            {},
            '/usr/bin/env bash -c "SKIP_TFSEC=true SKIP_CHECKOV=true terraform plan || true"',
            0,
        ),
        (
            {},
            '/usr/bin/env bash -c "SKIP_TFSEC=true SKIP_CHECKOV=true terraform plan || true && false"',
            1,
        ),
        (
            {},
            '/usr/bin/env bash -c "SKIP_TFSEC=true SKIP_CHECKOV=true terraform plan || false"',
            1,
        ),
        ({"SKIP_CHECKOV": "true"}, "terraform plan --skip-tfsec", 3),
        ({"SKIP_TFSEC": "true"}, "terraform plan --skip-checkov", 3),
        ({"SKIP_CHECKOV": "true", "SKIP_TFSEC": "true"}, "terraform plan", 3),
        (
            {"SKIP_CHECKOV": "true", "SKIP_TFSEC": "true"},
            "terraform plan --skip-checkov --skip-tfsec",
            3,
        ),
    ]

    num_tests_ran += exec_terraform(tests=tests, volumes=terrascan_volumes, image=image)

    # Ensure insecure configurations still succeed when security checks are
    # disabled
    # Tests is a list of tuples containing the test environment, command, and
    # expected exit code
    tests: list[tuple[dict, str, int]] = [
        ({"DISABLE_SECURITY": "true"}, "terraform init", 0),
        (
            {"DISABLE_SECURITY": "true"},
            '/usr/bin/env bash -c "DISABLE_SECURITY=true terraform init"',
            0,
        ),
        ({}, '/usr/bin/env bash -c "DISABLE_SECURITY=true terraform init"', 0),
        (
            {},
            '/usr/bin/env bash -c "DISABLE_SECURITY=true terraform --disable-security init"',
            0,
        ),
        (
            {},
            '/usr/bin/env bash -c "DISABLE_SECURITY=true terraform init --disable-security"',
            0,
        ),
        ({}, "terraform --disable-security init", 0),
        ({}, "terraform init --disable-security", 0),
        (
            {},
            '/usr/bin/env bash -c "DISABLE_SECURITY=true terraform init --disable-security || true"',
            0,
        ),
        (
            {},
            '/usr/bin/env bash -c "DISABLE_SECURITY=true terraform init --disable-security || true && false"',
            1,
        ),
        ({"DISABLE_SECURITY": "true"}, "terraform init", 0),
        (
            {"DISABLE_SECURITY": "true"},
            "terraform plan || false",
            1,
        ),  # Not supported; reproduce "Too many command line
        #     arguments. Configuration path expected." error locally with
        #     `docker run -e DISABLE_SECURITY=true -v
        #     $(pwd)/tests/terraform/terrascan:/iac
        #     seiso/easy_infra:latest terraform plan \|\| false`, prefer
        #     passing the commands through bash like the following test
        (
            {"DISABLE_SECURITY": "true"},
            '/usr/bin/env bash -c "terraform plan || false"',
            1,
        ),
        (
            {"DISABLE_SECURITY": "true"},
            '/usr/bin/env bash -c "terraform plan || true"',
            0,
        ),
        (
            {},
            "DISABLE_SECURITY=true terraform plan",
            127,
        ),  # Not supported; prepended variables do not work unless the
        #     commands are passed through bash
    ]

    num_tests_ran += exec_terraform(tests=tests, volumes=terrascan_volumes, image=image)

    # Ensure secure configurations pass
    # Tests is a list of tuples containing the test environment, command, and
    # expected exit code
    tests: list[tuple[dict, str, int]] = [
        ({}, "terraform init", 0),
        (
            {},
            '/bin/bash -c "terraform init && terraform validate && echo no | terraform apply"',
            1,
        ),  # Getting Started example from the README.md (Minimally modified for automation)
        (
            {},
            '/bin/bash -c "terraform init; terraform version"',
            0,
        ),  # Terraform Caching example from the README.md
        (
            {},
            '/usr/bin/env bash -c "terraform init && terraform validate && terraform plan && terraform validate"',
            0,
        ),
        (
            {},
            '/usr/bin/env bash -c "terraform init && terraform validate && terraform plan && terraform validate && false"',
            1,
        ),
    ]

    num_tests_ran += exec_terraform(tests=tests, volumes=secure_volumes, image=image)

    # Run base interactive tests
    test_interactive_container = constants.CLIENT.containers.run(
        image=image,
        detach=True,
        auto_remove=False,
        tty=True,
        volumes=secure_volumes,
        environment=environment,
    )

    # Running an interactive terraform command should not cause the creation of
    # the following files
    test_interactive_container.exec_run(
        cmd='/bin/bash -ic "terraform validate"', tty=True
    )
    files = ["/tfsec_complete", "/terrascan_complete", "/checkov_complete"]
    for file in files:
        # attempt is a tuple of (exit_code, output)
        attempt = test_interactive_container.exec_run(cmd=f"ls {file}")
        if attempt[0] == 0:
            test_interactive_container.kill()
            LOG.error("Found the file %s when it was not expected", file)
            sys.exit(1)
        num_tests_ran += 1

    # Cleanup
    test_interactive_container.kill()

    # Run base non-interactive tests
    test_noninteractive_container = constants.CLIENT.containers.run(
        image=image,
        detach=True,
        auto_remove=False,
        tty=True,
        volumes=secure_volumes,
        environment=environment,
    )

    # Running a non-interactive terraform command should cause the creation of
    # the following files
    test_noninteractive_container.exec_run(
        cmd='/bin/bash -c "terraform validate"', tty=False
    )
    files = ["/tfsec_complete", "/terrascan_complete", "/checkov_complete"]
    for file in files:
        # attempt is a tuple of (exit_code, output)
        attempt = test_noninteractive_container.exec_run(cmd=f"ls {file}", tty=False)
        if attempt[0] != 0:
            test_noninteractive_container.kill()
            LOG.error(
                "Received an unexpected status code of %s; additional details: %s",
                attempt[0],
                attempt[1].decode("UTF-8").replace("\n", " ").strip(),
            )
            sys.exit(attempt[0])
        num_tests_ran += 1

    # Cleanup
    test_noninteractive_container.kill()

    # Run terraform version non-interactive test
    test_noninteractive_container = constants.CLIENT.containers.run(
        image=image,
        detach=True,
        auto_remove=False,
        tty=True,
        volumes=secure_volumes,
        environment=environment,
    )

    # Running a non-interactive terraform version (or any other supported
    # "version" argument) should NOT cause the creation of the following files
    test_noninteractive_container.exec_run(
        cmd='/bin/bash -c "terraform version"', tty=False
    )
    files = ["/tfsec_complete", "/terrascan_complete", "/checkov_complete"]
    for file in files:
        # attempt is a tuple of (exit_code, output)
        attempt = test_noninteractive_container.exec_run(cmd=f"ls {file}", tty=False)
        if attempt[0] == 0:
            test_interactive_container.kill()
            LOG.error("Found the file %s when it was not expected", file)
            sys.exit(1)
        num_tests_ran += 1

    # Cleanup
    test_noninteractive_container.kill()

    LOG.info("%s passed %d end to end terraform tests", image, num_tests_ran)


def run_az_stage(*, image: str):
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


def run_aws_stage(*, image: str):
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


def run_cli(*, image: str):
    """Run basic cli tests"""
    num_tests_ran = 0

    # Ensure a basic aws help command succeeds
    command = "aws help"
    opinionated_docker_run(image=image, command=command, expected_exit=0)
    num_tests_ran += 1

    # Ensure a basic azure help command succeeds
    command = "az help"
    opinionated_docker_run(image=image, command=command, expected_exit=0)
    num_tests_ran += 1

    LOG.info("%s passed %d integration tests", image, num_tests_ran)


def run_security(*, image: str):
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
    file_name = f"{tag}.tar"
    image_file = temp_dir.joinpath(file_name)
    raw_image = constants.CLIENT.images.get(image).save(named=True)
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
