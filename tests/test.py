#!/usr/bin/env python3
"""
Test Functions
"""

import copy
import os
import sys
from logging import getLogger
from pathlib import Path

import docker
from easy_infra import constants, utils

# Globals
CONFIG = utils.parse_config(config_file=constants.CONFIG_FILE)
CWD = Path(".").absolute()
TESTS_PATH = CWD.joinpath("tests")

LOG = getLogger(__name__)

CLIENT = docker.from_env()


def version_arguments(*, image: str, volumes: dict, working_dir: str):
    """Test the version arguments listed in the config"""
    num_tests_ran = 0
    for command in CONFIG["commands"]:
        if "version_argument" not in CONFIG["commands"][command]:
            continue

        if "aliases" in CONFIG["commands"][command]:
            aliases = CONFIG["commands"][command]["aliases"]
        else:
            aliases = [command]

        for alias in aliases:
            docker_command = (
                f'command {alias} {CONFIG["commands"][command]["version_argument"]}'
            )
            utils.opinionated_docker_run(
                image=image,
                volumes=volumes,
                working_dir=working_dir,
                command=docker_command,
                expected_exit=0,
            )
            num_tests_ran += 1

    LOG.info("%s passed %d integration tests", image, num_tests_ran)


def check_for_files(
    *,
    container: docker.models.containers.Container,
    files: list,
    expected_to_exist: bool,
) -> int:
    """
    Check for the provided list of files in the provided container and return
    0 for any failures, or the number of correctly found files
    """
    successful_tests = 0

    for file in files:
        # attempt is a tuple of (exit_code, output)
        attempt = container.exec_run(cmd=f"ls {file}")
        if (expected_to_exist and attempt[0] != 0) or (
            not expected_to_exist and attempt[0] == 0
        ):
            container.kill()
            if expected_to_exist:
                LOG.error("Didn't find the file %s when it was expected", file)
            elif not expected_to_exist:
                LOG.error("Found the file %s when it was not expected", file)
            return 0
        successful_tests += 1

    container.kill()

    return successful_tests


def run_path_check(*, image: str) -> None:
    """Wrapper to run check_paths"""
    for interactive in [True, False]:
        num_successful_tests = check_paths(interactive=interactive, image=image)
        if num_successful_tests > 0:
            LOG.info("%s passed all %d path tests", image, num_successful_tests)
        else:
            LOG.error("%s failed a path test", image)
            sys.exit(1)


def check_paths(*, interactive: bool, image: str) -> int:
    """
    Check all of the commands in easy_infra.yml to ensure they are in the
    easy_infra user's PATH. Return 0 for any failures, or the number of
    correctly found files
    """
    container = CLIENT.containers.run(
        image=image,
        detach=True,
        auto_remove=False,
        tty=True,
    )

    # All commands should be in the PATH of the easy_infra user
    LOG.debug("Testing the easy_infra user's PATH when interactive is %s", interactive)
    num_successful_tests = 0
    for command in CONFIG["commands"]:
        if "aliases" in CONFIG["commands"][command]:
            aliases = CONFIG["commands"][command]["aliases"]
        else:
            aliases = [command]

        for alias in aliases:
            if interactive:
                attempt = container.exec_run(
                    cmd=f'/bin/bash -ic "which {alias}"', tty=True
                )
            else:
                attempt = container.exec_run(
                    cmd=f'/bin/bash -c "which {alias}"',
                )
            if attempt[0] != 0:
                LOG.error("%s is not in the easy_infra PATH", alias)
                container.kill()
                return 0

            num_successful_tests += 1

    container.kill()
    return num_successful_tests


def exec_tests(
    *,
    tests: list[tuple[dict, str, int]],
    volumes: dict,
    image: str,
) -> int:
    """Execute the provided tests and return a count of tests run"""
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
        utils.opinionated_docker_run(
            command=command,
            environment=environment,
            expected_exit=expected_exit,
            image=image,
            volumes=volumes,
            working_dir=working_dir,
        )
        num_tests_ran += 1
    return num_tests_ran


def run_terraform(*, image: str, final: bool = False):
    """Run the terraform tests"""
    num_tests_ran = 0
    working_dir = "/iac/"
    environment = {"TF_DATA_DIR": "/tmp"}
    tests_test_dir = TESTS_PATH
    tests_volumes = {tests_test_dir: {"bind": working_dir, "mode": "ro"}}
    invalid_test_dir = TESTS_PATH.joinpath("terraform/invalid")
    invalid_volumes = {invalid_test_dir: {"bind": working_dir, "mode": "rw"}}
    tfsec_test_dir = TESTS_PATH.joinpath("terraform/tfsec")
    tfsec_volumes = {tfsec_test_dir: {"bind": working_dir, "mode": "rw"}}
    checkov_test_dir = TESTS_PATH.joinpath("terraform/checkov")
    checkov_volumes = {checkov_test_dir: {"bind": working_dir, "mode": "rw"}}
    terrascan_test_dir = TESTS_PATH.joinpath("terraform/terrascan")
    terrascan_volumes = {terrascan_test_dir: {"bind": working_dir, "mode": "rw"}}
    kics_config_dir = TESTS_PATH.joinpath("terraform/kics")
    kics_volumes = {kics_config_dir: {"bind": working_dir, "mode": "rw"}}
    secure_config_dir = TESTS_PATH.joinpath("terraform/secure")
    secure_volumes = {secure_config_dir: {"bind": working_dir, "mode": "rw"}}

    # Base tests
    command = "./test.sh"
    LOG.debug("Running test.sh")
    utils.opinionated_docker_run(
        image=image,
        volumes=tests_volumes,
        command=command,
        expected_exit=0,
    )
    num_tests_ran += 1

    # Ensure invalid configurations fail
    command = "terraform plan"
    LOG.debug("Testing invalid terraform configurations")
    utils.opinionated_docker_run(
        image=image,
        volumes=invalid_volumes,
        command=command,
        environment=environment,
        expected_exit=1,
    )
    num_tests_ran += 1

    # Test informational mode on an invalid configuration
    command = "terraform validate"
    LOG.debug("Testing informational mode on an invalid configuration")
    informational_environment = copy.deepcopy(environment)
    informational_environment["LEARNING_MODE"] = "true"
    utils.opinionated_docker_run(
        image=image,
        volumes=invalid_volumes,
        command=command,
        environment=informational_environment,
        expected_exit=1,  # This still fails terraform validate
    )
    num_tests_ran += 1

    # Ensure secure configurations pass
    # Tests is a list of tuples containing the test environment, command, and
    # expected exit code
    tests: list[tuple[dict, str, int]] = [  # type: ignore
        ({}, "terraform init", 0),
        ({}, "tfenv exec init", 0),
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

    LOG.debug("Testing secure terraform configurations")
    num_tests_ran += exec_tests(tests=tests, volumes=secure_volumes, image=image)

    # Ensure insecure configurations still succeed when security checks are
    # disabled
    # Tests is a list of tuples containing the test environment, command, and
    # expected exit code
    tests: list[tuple[dict, str, int]] = [  # type: ignore
        ({"DISABLE_SECURITY": "true"}, "terraform init", 0),
        ({"DISABLE_SECURITY": "true"}, "tfenv exec init", 0),
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

    LOG.debug("Testing terraform with security disabled")
    num_tests_ran += exec_tests(tests=tests, volumes=terrascan_volumes, image=image)

    # Ensure insecure configurations fail due to kics
    # Tests is a list of tuples containing the test environment, command, and
    # expected exit code
    tests: list[tuple[dict, str, int]] = [  # type: ignore
        ({}, "terraform --skip-tfsec --skip-terrascan --skip-checkov plan", 50),
        ({}, "tfenv exec --skip-tfsec --skip-terrascan --skip-checkov plan", 50),
        (
            {},
            '/usr/bin/env bash -c "SKIP_TFSEC=true SKIP_TERRASCAN=true SKIP_CHECKOV=true terraform plan"',
            50,
        ),
        (
            {},
            '/usr/bin/env bash -c "SKIP_TFSEC=true SKIP_TERRASCAN=true SKIP_CHECKOV=true terraform plan || true"',
            0,
        ),
        (
            {},
            '/usr/bin/env bash -c "SKIP_TFSEC=true SKIP_CHECKOV=true SKIP_TERRASCAN=true terraform plan || true && false"',
            1,
        ),
        (
            {},
            '/usr/bin/env bash -c "SKIP_TFSEC=true SKIP_CHECKOV=true SKIP_TERRASCAN=true terraform plan || false"',
            1,
        ),
        ({"SKIP_CHECKOV": "true"}, "terraform plan --skip-tfsec --skip-terrascan", 50),
        ({"SKIP_TFSEC": "true"}, "terraform --skip-terrascan plan --skip-checkov", 50),
        (
            {"SKIP_CHECKOV": "true", "SKIP_TFSEC": "true", "SKIP_TERRASCAN": "true"},
            "terraform plan",
            50,
        ),
        (
            {"SKIP_CHECKOV": "true", "SKIP_TFSEC": "true", "SKIP_TERRASCAN": "true"},
            "terraform plan --skip-checkov --skip-tfsec --skip-terrascan",
            50,
        ),
        (
            {},
            '/usr/bin/env bash -c "LEARNING_MODE=true SKIP_TFSEC=true SKIP_CHECKOV=true SKIP_TERRASCAN=true terraform validate"',
            0,
        ),
        (
            {"LEARNING_MODE": "true", "SKIP_CHECKOV": "true"},
            "terraform validate --skip-tfsec --skip-terrascan",
            0,
        ),
    ]

    num_tests_ran += exec_tests(tests=tests, volumes=kics_volumes, image=image)

    # Run base interactive terraform tests
    test_interactive_container = CLIENT.containers.run(
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
    files = ["/tmp/kics_complete"]
    if final:
        files.append("/tmp/tfsec_complete")
        files.append("/tmp/terrascan_complete")
        files.append("/tmp/checkov_complete")
    LOG.debug("Testing interactive terraform commands")
    if (
        num_successful_tests := check_for_files(
            container=test_interactive_container, files=files, expected_to_exist=False
        )
    ) == 0:
        sys.exit(1)

    num_tests_ran += num_successful_tests

    # Run base non-interactive tests for terraform
    test_noninteractive_container = CLIENT.containers.run(
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
    files = ["/tmp/kics_complete"]
    if final:
        files.append("/tmp/tfsec_complete")
        files.append("/tmp/terrascan_complete")
        files.append("/tmp/checkov_complete")
    LOG.debug("Testing non-interactive terraform commands")
    if (
        num_successful_tests := check_for_files(
            container=test_noninteractive_container, files=files, expected_to_exist=True
        )
    ) == 0:
        sys.exit(1)

    num_tests_ran += num_successful_tests

    # Run terraform version non-interactive test
    test_noninteractive_container = CLIENT.containers.run(
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
    files = ["/tmp/kics_complete"]
    if final:
        files.append("/tmp/tfsec_complete")
        files.append("/tmp/terrascan_complete")
        files.append("/tmp/checkov_complete")
    LOG.debug("Testing non-interactive terraform version")
    if (
        num_successful_tests := check_for_files(
            container=test_noninteractive_container,
            files=files,
            expected_to_exist=False,
        )
    ) == 0:
        sys.exit(1)

    num_tests_ran += num_successful_tests

    if not final:
        LOG.info("%s passed %d end to end terraform tests", image, num_tests_ran)
        return

    # Ensure insecure configurations fail due to tfsec
    # Tests is a list of tuples containing the test environment, command, and
    # expected exit code
    tests: list[tuple[dict, str, int]] = [  # type: ignore
        ({}, "terraform --skip-checkov --skip-terrascan --skip-kics plan", 1),
        ({}, "tfenv exec --skip-checkov --skip-kics --skip-terrascan plan", 1),
        (
            {},
            "SKIP_KICS=true SKIP_CHECKOV=true SKIP_TERRASCAN=true terraform plan",
            127,
        ),  # Not supported; prepended variables do not work unless the
        #     commands are passed through bash
        (
            {},
            '/usr/bin/env bash -c "SKIP_KICS=true SKIP_CHECKOV=true SKIP_TERRASCAN=true terraform plan"',
            1,
        ),
        (
            {"SKIP_CHECKOV": "true", "SKIP_KICS": "true"},
            '/usr/bin/env bash -c "SKIP_TERRASCAN=true terraform plan || true"',
            0,
        ),
        (
            {"SKIP_CHECKOV": "true"},
            '/usr/bin/env bash -c "SKIP_KICS=true SKIP_TERRASCAN=true terraform plan || true && false"',
            1,
        ),
        (
            {"SKIP_CHECKOV": "true", "SKIP_KICS": "true"},
            '/usr/bin/env bash -c "SKIP_TERRASCAN=true terraform plan || false"',
            1,
        ),
        ({"SKIP_CHECKOV": "true"}, "terraform --skip-kics --skip-terrascan plan", 1),
        (
            {"SKIP_TERRASCAN": "TRUE", "SKIP_KICS": "True"},
            "terraform --skip-checkov plan",
            1,
        ),
        ({"SKIP_KICS": "True"}, "terraform --skip-terrascan --skip-checkov plan", 1),
        (
            {"SKIP_TERRASCAN": "True", "SKIP_CHECKOV": "TrUe", "SKIP_KICS": "tRuE"},
            "terraform plan",
            1,
        ),
        (
            {"SKIP_TERRASCAN": "tRuE", "SKIP_CHECKOV": "FaLsE", "SKIP_KICS": "Unknown"},
            "terraform --skip-checkov plan --skip-terrascan --skip-kics",
            1,
        ),
        (
            {"SKIP_KICS": "TRUE", "SKIP_TERRASCAN": "tRuE", "SKIP_TFSEC": "false"},
            "terraform --skip-checkov --skip-kics plan --skip-terrascan",
            1,
        ),
        (
            {},
            '/usr/bin/env bash -c "terraform --skip-kics --skip-checkov --skip-terrascan plan || true"',
            0,
        ),
        (
            {
                "LEARNING_MODE": "TrUe",
                "SKIP_KICS": "TRUE",
                "SKIP_TERRASCAN": "tRuE",
                "SKIP_TFSEC": "false",
            },
            "terraform --skip-checkov --skip-kics validate --skip-terrascan",
            0,
        ),
        (
            {"LEARNING_MODE": "TRUE"},
            '/usr/bin/env bash -c "terraform --skip-kics --skip-checkov --skip-terrascan validate"',
            0,
        ),
    ]

    LOG.debug("Testing tfsec against insecure terraform")
    num_tests_ran += exec_tests(tests=tests, volumes=tfsec_volumes, image=image)

    # Ensure insecure configurations fail due to checkov
    # Tests is a list of tuples containing the test environment, command, and
    # expected exit code
    tests: list[tuple[dict, str, int]] = [  # type: ignore
        ({}, "terraform --skip-kics --skip-tfsec --skip-terrascan plan", 1),
        ({}, "tfenv exec --skip-tfsec --skip-kics --skip-terrascan plan", 1),
        (
            {},
            '/usr/bin/env bash -c "SKIP_TFSEC=true SKIP_KICS=true SKIP_TERRASCAN=true terraform plan"',
            1,
        ),
        (
            {"SKIP_TFSEC": "true", "SKIP_KICS": "true"},
            '/usr/bin/env bash -c "SKIP_TERRASCAN=true terraform plan || true"',
            0,
        ),
        (
            {"SKIP_TFSEC": "true"},
            '/usr/bin/env bash -c "SKIP_TERRASCAN=true SKIP_KICS=true terraform plan || true && false"',
            1,
        ),
        (
            {"SKIP_TFSEC": "true", "SKIP_KICS": "TRUE"},
            '/usr/bin/env bash -c "SKIP_TERRASCAN=true terraform plan || false"',
            1,
        ),
        (
            {"SKIP_TFSEC": "true", "SKIP_KICS": "true"},
            "terraform plan --skip-terrascan",
            1,
        ),
        (
            {"SKIP_TERRASCAN": "true", "SKIP_KICS": "true"},
            "terraform --skip-tfsec plan",
            1,
        ),
        (
            {"SKIP_TFSEC": "true", "SKIP_KICS": "true"},
            "terraform --skip-tfsec --skip-kics plan --skip-terrascan",
            1,
        ),
        (
            {"SKIP_TERRASCAN": "true", "SKIP_KICS": "true", "SKIP_TFSEC": "true"},
            "terraform --skip-tfsec plan --skip-terrascan --skip-kics",
            1,
        ),
        (
            {"LEARNING_MODE": "tRuE", "SKIP_TFSEC": "true", "SKIP_KICS": "TRUE"},
            '/usr/bin/env bash -c "SKIP_TERRASCAN=true terraform validate"',
            0,
        ),
        (
            {"LEARNING_MODE": "tRuE", "SKIP_TFSEC": "true", "SKIP_KICS": "true"},
            "terraform validate --skip-terrascan",
            0,
        ),
    ]

    LOG.debug("Testing checkov against insecure terraform")
    num_tests_ran += exec_tests(tests=tests, volumes=checkov_volumes, image=image)

    # Ensure insecure configurations fail due to terrascan
    # Tests is a list of tuples containing the test environment, command, and
    # expected exit code
    tests: list[tuple[dict, str, int]] = [  # type: ignore
        ({}, "terraform --skip-tfsec --skip-kics --skip-checkov plan", 3),
        ({}, "tfenv exec --skip-tfsec --skip-kics --skip-checkov plan", 3),
        (
            {},
            '/usr/bin/env bash -c "SKIP_TFSEC=true SKIP_KICS=true SKIP_CHECKOV=true terraform plan"',
            3,
        ),
        (
            {},
            '/usr/bin/env bash -c "SKIP_TFSEC=true SKIP_KICS=true SKIP_CHECKOV=true terraform plan || true"',
            0,
        ),
        (
            {},
            '/usr/bin/env bash -c "SKIP_TFSEC=true SKIP_CHECKOV=true SKIP_KICS=true terraform plan || true && false"',
            1,
        ),
        (
            {},
            '/usr/bin/env bash -c "SKIP_TFSEC=true SKIP_CHECKOV=true SKIP_KICS=true terraform plan || false"',
            1,
        ),
        ({"SKIP_CHECKOV": "true"}, "terraform plan --skip-tfsec --skip-kics", 3),
        ({"SKIP_TFSEC": "true"}, "terraform --skip-kics plan --skip-checkov", 3),
        (
            {"SKIP_CHECKOV": "true", "SKIP_TFSEC": "true", "SKIP_KICS": "true"},
            "terraform plan",
            3,
        ),
        (
            {"SKIP_CHECKOV": "true", "SKIP_TFSEC": "true", "SKIP_KICS": "true"},
            "terraform plan --skip-checkov --skip-tfsec --skip-kics",
            3,
        ),
        (
            {},
            '/usr/bin/env bash -c "LEARNING_MODE=true SKIP_TFSEC=true SKIP_CHECKOV=true SKIP_KICS=true terraform validate"',
            0,
        ),
        (
            {"LEARNING_MODE": "true", "SKIP_CHECKOV": "true"},
            "terraform validate --skip-tfsec --skip-kics",
            0,
        ),
    ]

    LOG.debug("Testing terrascan against insecure terraform")
    num_tests_ran += exec_tests(tests=tests, volumes=terrascan_volumes, image=image)

    LOG.info("%s passed %d end to end terraform tests", image, num_tests_ran)


def run_ansible(*, image: str):
    """Run the ansible-playbook tests"""
    num_tests_ran = 0
    working_dir = "/iac/"
    kics_config_dir = TESTS_PATH.joinpath("ansible/kics")
    kics_volumes = {kics_config_dir: {"bind": working_dir, "mode": "rw"}}
    secure_config_dir = TESTS_PATH.joinpath("ansible/secure")
    secure_volumes = {secure_config_dir: {"bind": working_dir, "mode": "rw"}}

    # Ensure insecure configurations fail due to kics
    # Tests is a list of tuples containing the test environment, command, and
    # expected exit code
    tests: list[tuple[dict, str, int]] = [
        ({}, "ansible-playbook insecure.yml --check", 50),
        (
            {},
            "ansible-playbook --skip-kics insecure.yml --check",
            4,
        ),  # Exits 4 because insecure.yml is not a valid Play
        (
            {},
            "SKIP_KICS=true ansible-playbook insecure.yml --check",
            127,
        ),  # Not supported; prepended variables do not work unless the
        #     commands are passed through bash
        (
            {},
            '/usr/bin/env bash -c "SKIP_KICS=true ansible-playbook insecure.yml --check"',
            4,
        ),  # Exits 4 because insecure.yml is not a valid Play
        (
            {},
            '/usr/bin/env bash -c "ansible-playbook insecure.yml --check || true"',
            0,
        ),
        (
            {},
            '/usr/bin/env bash -c "SKIP_TFSEC=true ansible-playbook insecure.yml --check || true && false"',
            1,
        ),  # tfsec is purposefully irrelevant for ansible
        (
            {"SKIP_CHECKOV": "true", "SKIP_TERRASCAN": "true"},
            '/usr/bin/env bash -c "ansible-playbook insecure.yml --check || false"',
            1,
        ),  # checkov and terrascan are purposefully irrelevant for ansible
        (
            {"SKIP_TERRASCAN": "tRuE", "SKIP_CHECKOV": "FaLsE", "SKIP_KICS": "Unknown"},
            "ansible-playbook insecure.yml --check",
            50,
        ),  # checkov and terrascan are purposefully irrelevant for ansible
        (
            {},
            '/usr/bin/env bash -c "LEARNING_MODE=true ansible-playbook insecure.yml --check"',
            4,
        ),  # Exits 4 because insecure.yml is not a valid Play
        (
            {"LEARNING_MODE": "true"},
            "ansible-playbook insecure.yml --check",
            4,
        ),  # Exits 4 because insecure.yml is not a valid Play
    ]

    num_tests_ran += exec_tests(tests=tests, volumes=kics_volumes, image=image)

    # Run base interactive tests
    test_interactive_container = CLIENT.containers.run(
        image=image,
        detach=True,
        auto_remove=False,
        tty=True,
        volumes=secure_volumes,
    )

    # Running an interactive ansible-playbook command should not cause the creation of
    # the following files
    test_interactive_container.exec_run(
        cmd='/bin/bash -ic "ansible-playbook secure.yml --check"', tty=True
    )
    files = [
        "/tmp/kics_complete",
    ]
    LOG.debug("Testing interactive ansible-playbook commands")
    if (
        num_successful_tests := check_for_files(
            container=test_interactive_container, files=files, expected_to_exist=False
        )
    ) == 0:
        sys.exit(1)

    num_tests_ran += num_successful_tests

    # Run base non-interactive tests for ansible
    test_noninteractive_container = CLIENT.containers.run(
        image=image,
        detach=True,
        auto_remove=False,
        tty=True,
        volumes=secure_volumes,
    )

    # Running a non-interactive ansible-playbook command should cause the creation of
    # the following files
    test_noninteractive_container.exec_run(
        cmd='/bin/bash -c "ansible-playbook secure.yml --check"', tty=False
    )
    files = [
        "/tmp/kics_complete",
    ]
    LOG.debug("Testing non-interactive ansible-playbook commands")
    if (
        num_successful_tests := check_for_files(
            container=test_noninteractive_container, files=files, expected_to_exist=True
        )
    ) == 0:
        sys.exit(1)

    num_tests_ran += num_successful_tests

    # Run ansible-playbook version non-interactive test
    test_noninteractive_container = CLIENT.containers.run(
        image=image,
        detach=True,
        auto_remove=False,
        tty=True,
        volumes=secure_volumes,
    )

    # Running a non-interactive ansible-playbook version (or any other supported
    # "version" argument) should NOT cause the creation of the following files
    test_noninteractive_container.exec_run(
        cmd='/bin/bash -c "ansible-playbook --version"', tty=False
    )
    files = [
        "/tmp/kics_complete",
    ]
    LOG.debug("Testing non-interactive ansible-playbook version command")
    if (
        num_successful_tests := check_for_files(
            container=test_noninteractive_container,
            files=files,
            expected_to_exist=False,
        )
    ) == 0:
        sys.exit(1)

    num_tests_ran += num_successful_tests

    LOG.info("%s passed %d end to end ansible-playbook tests", image, num_tests_ran)


def run_az_stage(*, image: str):
    """Run the az tests"""
    num_tests_ran = 0

    # Ensure a basic azure help command succeeds
    command = "az help"
    utils.opinionated_docker_run(image=image, command=command, expected_exit=0)
    num_tests_ran += 1

    # Ensure a basic aws help command fails
    command = "aws help"
    utils.opinionated_docker_run(image=image, command=command, expected_exit=127)
    num_tests_ran += 1

    LOG.info("%s passed %d integration tests", image, num_tests_ran)


def run_aws_stage(*, image: str):
    """Run the aws tests"""
    num_tests_ran = 0

    # Ensure a basic aws help command succeeds
    command = "aws help"
    utils.opinionated_docker_run(image=image, command=command, expected_exit=0)
    num_tests_ran += 1

    # Ensure a basic az help command fails
    command = "az help"
    utils.opinionated_docker_run(image=image, command=command, expected_exit=127)
    num_tests_ran += 1

    LOG.info("%s passed %d integration tests", image, num_tests_ran)


def run_cli(*, image: str):
    """Run basic cli tests"""
    num_tests_ran = 0

    # Ensure a basic aws help command succeeds
    command = "aws help"
    utils.opinionated_docker_run(image=image, command=command, expected_exit=0)
    num_tests_ran += 1

    # Ensure a basic azure help command succeeds
    command = "az help"
    utils.opinionated_docker_run(image=image, command=command, expected_exit=0)
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
    raw_image = CLIENT.images.get(image).save(named=True)
    with open(image_file, "wb") as file:
        for chunk in raw_image:
            file.write(chunk)

    working_dir = "/tmp/"
    volumes = {temp_dir: {"bind": working_dir, "mode": "ro"}}

    num_tests_ran = 0
    scanner = "aquasec/trivy:0.18.3"

    # Provide debug information about unknown, low, and medium severity
    # findings
    command = (
        "--quiet image --exit-code 0 --severity "
        + ",".join(constants.INFORMATIONAL_VULNS)
        + " --format json --light --input "
        + working_dir
        + file_name
    )
    utils.opinionated_docker_run(
        image=scanner, command=command, volumes=volumes, expected_exit=0
    )
    num_tests_ran += 1

    # Ensure no critical vulnerabilities exist in the image
    command = (
        "--quiet image --exit-code 1 --severity "
        + ",".join(constants.UNACCEPTABLE_VULNS)
        + " --format json --light --input "
        + working_dir
        + file_name
    )
    utils.opinionated_docker_run(
        image=scanner, command=command, volumes=volumes, expected_exit=0
    )
    num_tests_ran += 1

    LOG.info("%s passed %d security tests", image, num_tests_ran)
