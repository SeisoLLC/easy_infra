#!/usr/bin/env python3
"""
Test Functions
"""

import copy
import subprocess
import sys
from logging import getLogger
from pathlib import Path
from typing import Union

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
        # container.exec_run returns a tuple of (exit_code, output)
        exit_code = container.exec_run(cmd=f"ls {file}")[0]
        if (expected_to_exist and exit_code != 0) or (
            not expected_to_exist and exit_code == 0
        ):
            if expected_to_exist:
                LOG.error("Didn't find the file %s when it was expected", file)
            elif not expected_to_exist:
                LOG.error("Found the file %s when it was not expected", file)
            return 0
        successful_tests += 1

    return successful_tests


def is_expected_file_length(
    *,
    container: docker.models.containers.Container,
    log_path: str,
    expected_log_length: int,
) -> bool:
    """
    Compare the number of lines in the provided file_path to the provided
    expected length, in the provided container. Return True if the file length
    is expected, else False
    """
    exit_code, output = container.exec_run(
        cmd=f"/bin/bash -c \"set -o pipefail; wc -l {log_path} | awk '{{print $1}}'\""
    )
    sanitized_output = int(output.decode("utf-8").strip())
    if exit_code != 0:
        LOG.error("The provided container exited with an exit code of %s", exit_code)
        return False

    if sanitized_output != expected_log_length:
        LOG.error(
            "The file %s had a length of %s when a length of %s was expected",
            log_path,
            sanitized_output,
            expected_log_length,
        )
        return False

    return True


def check_container(
    container: docker.models.containers.Container,
    log_path: str,
    expected_log_length: int,
    files: Union[list, None] = None,
    files_expected_to_exist: bool = True,
) -> int:
    """
    Checks a provided container for:
    - Whether the provided files list exists as expected (optional)
    - Whether the fluent bit log length is expected

    Returns 0 if any test fails, otherwise the number of successful tests
    """
    num_successful_tests = 0

    if files:
        if (
            num_successful_tests := check_for_files(
                container=container,
                files=files,
                expected_to_exist=files_expected_to_exist,
            )
        ) == 0:
            return 0

    if not is_expected_file_length(
        container=container, log_path=log_path, expected_log_length=expected_log_length
    ):
        return 0

    num_successful_tests += 1

    return num_successful_tests


def run_path_check(*, image: str) -> None:
    """Wrapper to run check_paths"""
    for interactive in [True, False]:
        num_successful_tests = check_paths(interactive=interactive, image=image)
        if num_successful_tests > 0:
            context = "interactive" if interactive else "non-interactive"
            LOG.info(f"{image} passed all {num_successful_tests} {context} path tests")
        else:
            context = "an interactive" if interactive else "a non-interactive"
            LOG.error(f"{image} failed {context} path test")
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
    network_mode: Union[str, None] = None,
) -> int:
    """Execute the provided tests and return a count of tests run"""
    num_tests_ran = 0
    config_dir = list(volumes.keys())[0]
    working_dir = volumes[config_dir]["bind"]

    for environment, command, expected_exit in tests:
        LOG.debug(f"{environment=}, {command=}, {expected_exit=}")
        utils.opinionated_docker_run(
            command=command,
            environment=environment,
            expected_exit=expected_exit,
            image=image,
            volumes=volumes,
            working_dir=working_dir,
            network_mode=network_mode,
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
    invalid_test_dir = TESTS_PATH.joinpath("terraform/general/invalid")
    invalid_volumes = {invalid_test_dir: {"bind": working_dir, "mode": "rw"}}
    checkov_test_dir = TESTS_PATH.joinpath("terraform/tool/checkov")
    checkov_volumes = {checkov_test_dir: {"bind": working_dir, "mode": "rw"}}
    kics_config_dir = TESTS_PATH.joinpath("terraform/tool/kics")
    kics_volumes = {kics_config_dir: {"bind": working_dir, "mode": "rw"}}
    secure_config_dir = TESTS_PATH.joinpath("terraform/general/secure")
    secure_volumes = {secure_config_dir: {"bind": working_dir, "mode": "rw"}}
    general_test_dir = TESTS_PATH.joinpath("terraform/general")
    general_test_volumes = {general_test_dir: {"bind": working_dir, "mode": "rw"}}
    hooks_config_dir = TESTS_PATH.joinpath("terraform/hooks")
    hooks_config_volumes = {hooks_config_dir: {"bind": working_dir, "mode": "rw"}}
    fluent_bit_config_host = TESTS_PATH.joinpath("fluent-bit.outputs.conf")
    fluent_bit_config_container = "/usr/local/etc/fluent-bit/fluent-bit.outputs.conf"
    secure_volumes_with_log_config = copy.deepcopy(secure_volumes)
    secure_volumes_with_log_config[fluent_bit_config_host] = {
        "bind": fluent_bit_config_container,
        "mode": "ro",
    }
    hooks_secure_terraform_v_1_3_dir = TESTS_PATH.joinpath("terraform/hooks/secure_1_3")
    hooks_secure_terraform_v_1_3_dir_volumes = {
        hooks_secure_terraform_v_1_3_dir: {"bind": working_dir, "mode": "rw"}
    }
    hooks_secure_terraform_v_0_14_dir = TESTS_PATH.joinpath(
        "terraform/hooks/secure_0_14"
    )
    hooks_secure_terraform_v_0_14_dir_volumes = {
        hooks_secure_terraform_v_0_14_dir: {"bind": working_dir, "mode": "rw"}
    }
    report_base_dir = Path("/tmp/reports")
    kics_output_file = report_base_dir.joinpath("kics").joinpath("kics.json")
    checkov_output_file = report_base_dir.joinpath("checkov").joinpath("checkov.json")

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

    # Ensure autodetect finds the appropriate terraform configs, which can be inferred by the number of logs written to /var/log/easy_infra.log
    #
    # This test requires LEARNING_MODE to be true because the autodetect functionality traverses into the testing sub-directories, including those
    # which are purposefully insecure, which otherwise would exit non-zero early, resulting in a limited set of logs.
    # There is always one log for each security tool, regardless of if that tool is installed in the image being used.  If a tool is not in the PATH
    # and executable, a log message indicating that is generated.
    number_of_security_tools = len(CONFIG["commands"]["terraform"]["security"])
    # This list needs to be sorted because it uses pathlib's rglob, which (currently) uses os.scandir, which is documented to yield entries in
    # arbitrary order https://docs.python.org/3/library/os.html#os.scandir
    general_test_dirs = [dir for dir in general_test_dir.rglob("*") if dir.is_dir()]
    general_test_dirs.sort()
    general_test_dirs_containing_only_files = []
    for directory in general_test_dirs:
        items_in_dir = directory.iterdir()
        for item in items_in_dir:
            if item.is_dir():
                break
        else:
            general_test_dirs_containing_only_files.append(directory)
    number_of_testing_dirs = len(general_test_dirs_containing_only_files)
    learning_mode_and_autodetect_environment = copy.deepcopy(informational_environment)
    learning_mode_and_autodetect_environment["DISABLE_HOOKS"] = "true"
    LOG.debug("Testing LEARNING_MODE with various AUTODETECT configurations")

    tests: list[tuple[dict, str, int]] = []
    for autodetect_status in ["true", "false"]:
        if autodetect_status == "true":
            # Since DISABLE_HOOKS is true, there is one log per number_of_testing_dirs saying that hooks are disabled
            expected_number_of_logs = (
                number_of_security_tools * number_of_testing_dirs
                + number_of_testing_dirs
            )
        else:
            # Since DISABLE_HOOKS is true and AUTODETECT is false, there is one log added saying that hooks are disabled in the working dir
            expected_number_of_logs = number_of_security_tools + 1
        test_log_length = (
            "actual_number_of_logs=$(wc -l /var/log/easy_infra.log | awk '{print $1}'); "
            + f"if [[ ${{actual_number_of_logs}} != {expected_number_of_logs} ]]; then "
            + f'echo \\"/var/log/easy_infra.log had a length of ${{actual_number_of_logs}} when a length of {expected_number_of_logs} was expected\\"; '
            + "exit 230; fi"
        )
        actual = 6
        expected = 9
        command = f'/bin/bash -c "terraform init -backend=false && {test_log_length}"'
        learning_mode_and_autodetect_environment["AUTODETECT"] = autodetect_status
        tests.append(
            (copy.deepcopy(learning_mode_and_autodetect_environment), command, 0)
        )

    num_tests_ran += exec_tests(tests=tests, volumes=general_test_volumes, image=image)

    # Ensure autodetect finds the appropriate terraform configs, which can be inferred by the number of logs written to /var/log/easy_infra.log
    #
    # This test ensure that, when DISABLE_SECURITY is true, the provided command is still run for each of the testing sub-directories. It will exit
    # non-zero on the first instance of a failed command, which should occur only when it encounters an invalid configuration. Hooks are also disabled
    # for simplicity
    disable_security_environment = copy.deepcopy(environment)
    disable_security_status = "true"
    disable_security_environment["DISABLE_SECURITY"] = disable_security_status
    disable_security_and_autodetect_environment = copy.deepcopy(
        disable_security_environment
    )
    disable_security_and_autodetect_environment["DISABLE_HOOKS"] = "true"
    LOG.debug(
        "Testing the exit statuses and the number of logs generated based on various autodetect and disable security settings (Hooks are disabled)"
    )
    for autodetect_status in ["true", "false"]:
        disable_security_and_autodetect_environment["AUTODETECT"] = autodetect_status
        command = "terraform validate"

        if autodetect_status == "true":
            # Expect exit 1 due to the discovery of terraform/general/invalid/invalid.tf
            expected_exit = 1
        elif autodetect_status == "false":
            # Expect exit 0 because the command is ran in terraform/general and doesn't discover subdirs
            expected_exit = 0

        utils.opinionated_docker_run(
            image=image,
            command=command,
            volumes=general_test_volumes,
            environment=disable_security_and_autodetect_environment,
            expected_exit=expected_exit,
        )

        num_tests_ran += 1

        # Test the number of logs generated based on the current autodetect and disable security environment variables
        test_autodetect_disable_security_container = CLIENT.containers.run(
            image=image,
            detach=True,
            auto_remove=False,
            tty=True,
            volumes=general_test_volumes,
            environment=disable_security_and_autodetect_environment,
        )

        if autodetect_status == "true":
            # Use the index of the 'invalid' dir as the expected number of logs, since it fails at invalid, + 1 to adjust for 0-indexing. Note that
            # the general_test_dirs list needs to be alphabetically sorted
            invalid_dir_index = general_test_dirs.index(invalid_test_dir) + 1
            # One log for each folder that would be encountered
            logs_from_disable_hooks = invalid_dir_index
            expected_number_of_logs = invalid_dir_index + logs_from_disable_hooks
        else:
            # If DISABLE_SECURITY is true, one log is generated per dir where the related command is run. Since AUTODETECT is false, the related
            # command is only run in a single dir.
            number_of_commands = 1
            number_of_dirs = 1
            logs_from_disable_hooks = 1
            expected_number_of_logs = (
                number_of_commands * number_of_dirs + logs_from_disable_hooks
            )

        test_autodetect_disable_security_container.exec_run(
            cmd='/bin/bash -c "terraform validate || true"', tty=False
        )

        if (
            num_successful_tests := check_container(
                container=test_autodetect_disable_security_container,
                log_path="/var/log/easy_infra.log",
                expected_log_length=expected_number_of_logs,
            )
        ) == 0:
            test_autodetect_disable_security_container.kill()
            sys.exit(230)

        test_autodetect_disable_security_container.kill()

        num_tests_ran += num_successful_tests

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
        ),  # Previous Getting Started example from the README.md (Minimally modified for automation)
        (
            {},
            '/bin/bash -c "terraform init; terraform version"',
            0,
        ),  # Previous Terraform Caching example from the README.md
        (
            {},
            '/usr/bin/env bash -c "terraform validate && terraform plan && terraform validate"',
            0,
        ),
        (
            {},
            '/usr/bin/env bash -c "terraform init && terraform validate && false"',
            1,
        ),
        (
            {
                "KICS_INCLUDE_QUERIES": "4728cd65-a20c-49da-8b31-9c08b423e4db,46883ce1-dc3e-4b17-9195-c6a601624c73"
            },
            "terraform init",
            0,
        ),  # This tests "customizations" features from easy_infra.yml and functions.j2
        (
            {"KICS_EXCLUDE_SEVERITIES": "info"},
            "terraform validate",
            0,
        ),  # This tests "customizations" features from easy_infra.yml and functions.j2
    ]

    LOG.debug("Testing secure terraform configurations")
    num_tests_ran += exec_tests(tests=tests, volumes=secure_volumes, image=image)

    # Ensure the easy_infra hooks work as expected when network access is available
    # Tests is a list of tuples containing the test environment, command, and
    # expected exit code
    tests: list[tuple[dict, str, int]] = [  # type: ignore
        (
            {
                "DISABLE_HOOKS": "false",
                "AUTODETECT": "true",
                "DISABLE_SECURITY": "true",
            },
            '/bin/bash -c "terraform init -backend=false && terraform validate"',
            0,
        ),  # This tests the terraform version switching hook, regardless of the built-in security tools
        (
            {
                "DISABLE_HOOKS": "true",
                "AUTODETECT": "true",
                "DISABLE_SECURITY": "true",
            },
            '/bin/bash -c "terraform init -backend=false && terraform validate"',
            1,
        ),  # This tests DISABLE_HOOKS; it fails because the terraform version used is incorrect
    ]
    LOG.debug("Testing the easy_infra hooks against various terraform configurations")
    num_tests_ran += exec_tests(tests=tests, volumes=hooks_config_volumes, image=image)

    tests: list[tuple[dict, str, int]] = [  # type: ignore
        (
            {
                "DISABLE_HOOKS": "false",
                "AUTODETECT": "false",
                "DISABLE_SECURITY": "true",
                "TERRAFORM_VERSION": "1.1.8",
            },
            '/bin/bash -c "terraform init -backend=false && terraform validate"',
            1,
        ),  # This tests the bring-your-own TERRAFORM_VERSION hook (40-), regardless of the built-in security tools (DISABLE_SECURITY=true)
        # It fails because it ignores the 50- terraform due to AUTODETECT=false, and the v_0_14_dir files fail given the version of
        # TERRAFORM_VERSION specified above
    ]
    LOG.debug("Fail when using terraform 1.3.2 in a repo which expects 0.14.x")
    num_tests_ran += exec_tests(
        tests=tests,
        volumes=hooks_secure_terraform_v_0_14_dir_volumes,
        image=image,
    )

    # Ensure the easy_infra hooks work as expected when network access is NOT available
    # Tests is a list of tuples containing the test environment, command, and
    # expected exit code
    tests: list[tuple[dict, str, int]] = [  # type: ignore
        (
            {
                "DISABLE_HOOKS": "false",
                "AUTODETECT": "true",
                "DISABLE_SECURITY": "true",
            },
            '/bin/bash -c "terraform init -backend=false && terraform validate"',
            1,
        ),  # This tests the terraform version switching hook failback due to no network (see exec_tests below)
        # It fails because terraform/hooks/secure_0_14/secure.tf cannot be validated with the version of terraform
        # that TERRAFORM_VERSION indicates by default
    ]
    LOG.debug(
        "Testing the easy_infra hooks with no network access, against various terraform configurations, expecting failures"
    )
    num_tests_ran += exec_tests(
        tests=tests, volumes=hooks_config_volumes, image=image, network_mode="none"
    )

    tests: list[tuple[dict, str, int]] = [  # type: ignore
        (
            {
                "DISABLE_HOOKS": "false",
                "AUTODETECT": "true",
                "DISABLE_SECURITY": "true",
            },
            '/bin/bash -c "terraform init -backend=false && terraform validate"',
            0,
        ),  # This tests the terraform version switching hook failback due to no network (see exec_tests below)
        # It succeeds because only terraform/hooks/secure_1_3/secure.tf is tested, which will validate properly with the version of terraform that
        # TERRAFORM_VERSION indicates by default
        (
            {
                "DISABLE_HOOKS": "false",
                "AUTODETECT": "false",
                "DISABLE_SECURITY": "true",
                "TERRAFORM_VERSION": "1.1.8",
            },
            '/bin/bash -c "terraform init -backend=false && terraform validate"',
            0,
        ),  # This tests the bring-your-own TERRAFORM_VERSION hook, regardless of the built-in security tools
        # It succeeds because only terraform/hooks/secure_1_3/secure.tf is tested, and it requires a version of terraform newer then the provided
        # TERRAFORM_VERSION environment variable specifies, but because there is no network access the change does not take place
    ]
    LOG.debug(
        "Testing the easy_infra hooks with no network access, against various terraform configurations, expecting successes"
    )
    num_tests_ran += exec_tests(
        tests=tests,
        volumes=hooks_secure_terraform_v_1_3_dir_volumes,
        image=image,
        network_mode="none",
    )

    # Ensure insecure configurations still succeed when security checks are
    # disabled
    # Tests is a list of tuples containing the test environment, command, and
    # expected exit code
    tests: list[tuple[dict, str, int]] = [  # type: ignore
        ({"DISABLE_SECURITY": "true"}, "terraform init", 0),
        ({"DISABLE_SECURITY": "true"}, "tfenv exec init", 0),
        ({}, '/usr/bin/env bash -c "DISABLE_SECURITY=true terraform init"', 0),
        (
            {},
            '/usr/bin/env bash -c "DISABLE_SECURITY=true terraform --disable-security init"',
            0,
        ),
        ({}, "terraform --disable-security init", 0),  # Test order independence
        ({}, "terraform init --disable-security", 0),  # Test order independence
        (
            {},
            '/usr/bin/env bash -c "DISABLE_SECURITY=true terraform init --disable-security || true && false"',
            1,
        ),
        (
            {"DISABLE_SECURITY": "true"},
            "terraform plan || false",
            1,
        ),  # Not supported; reproduce "Too many command line
        #     arguments. Configuration path expected." error locally with
        #     `docker run -e DISABLE_SECURITY=true -v
        #     $(pwd)/tests/terraform/tool/checkov:/iac
        #     seiso/easy_infra:latest terraform plan \|\| false`, prefer
        #     passing the commands through bash like the following test
        (
            {},
            "DISABLE_SECURITY=true terraform plan",
            127,
        ),  # Not supported; prepended variables do not work unless the
        #     commands are passed through bash
        (
            {
                "KICS_INCLUDE_QUERIES": "4728cd65-a20c-49da-8b31-9c08b423e4db,46883ce1-dc3e-4b17-9195-c6a601624c73",  # Doesn't apply to kics_volumes
                "DISABLE_SECURITY": "true",
            },
            "terraform init",
            0,
        ),  # This tests the "customizations" idea from easy_infra.yml and functions.j2
        (
            {
                "KICS_INCLUDE_QUERIES": "5a2486aa-facf-477d-a5c1-b010789459ce",  # Would normally fail due to kics_volumes
                "DISABLE_SECURITY": "true",
            },
            "terraform init",
            0,
        ),  # This tests the "customizations" idea from easy_infra.yml and functions.j2
    ]

    LOG.debug("Testing terraform with security disabled")
    num_tests_ran += exec_tests(tests=tests, volumes=kics_volumes, image=image)

    # Ensure insecure configurations fail due to kics
    # Tests is a list of tuples containing the test environment, command, and
    # expected exit code
    tests: list[tuple[dict, str, int]] = [  # type: ignore
        ({}, "terraform --skip-checkov plan", 50),
        ({}, "tfenv exec --skip-checkov plan", 50),
        (
            {},
            '/usr/bin/env bash -c "SKIP_CHECKOV=true terraform plan"',
            50,
        ),
        (
            {},
            '/usr/bin/env bash -c "SKIP_CHECKOV=true terraform plan || true"',
            0,
        ),
        (
            {},
            '/usr/bin/env bash -c "SKIP_CHECKOV=true terraform plan || true && false"',
            1,
        ),
        ({"SKIP_CHECKOV": "true"}, "terraform plan --skip-checkov", 50),
        (
            {"SKIP_CHECKOV": "true"},
            "terraform plan",
            50,
        ),
        (
            {},
            '/usr/bin/env bash -c "LEARNING_MODE=true SKIP_CHECKOV=true terraform validate"',
            0,
        ),  # Test learning mode with skip env vars
        (
            {"LEARNING_MODE": "true", "SKIP_CHECKOV": "true"},
            "terraform validate",
            0,
        ),  # Test learning mode with mixed env vars and cli args
        (
            {
                "SKIP_CHECKOV": "true",
                "KICS_INCLUDE_QUERIES": "4728cd65-a20c-49da-8b31-9c08b423e4db,46883ce1-dc3e-4b17-9195-c6a601624c73",
            },
            "terraform validate",
            0,
        ),  # Exits with 0 because the provided insecure terraform does not apply to the included kics queries.
        # This tests the "customizations" idea from easy_infra.yml and functions.j2
        (
            {
                "SKIP_CHECKOV": "true",
                "KICS_INCLUDE_QUERIES": "5a2486aa-facf-477d-a5c1-b010789459ce",
            },
            "terraform validate",
            50,
        ),  # This tests the "customizations" idea from easy_infra.yml and functions.j2
        (
            {},
            '/usr/bin/env bash -c "KICS_INCLUDE_QUERIES=5a2486aa-facf-477d-a5c1-b010789459ce terraform --skip-checkov validate"',
            50,
        ),  # This tests the "customizations" idea from easy_infra.yml and functions.j2
        (
            {
                "SKIP_CHECKOV": "true",
                "KICS_EXCLUDE_SEVERITIES": "medium",
            },
            "terraform validate",
            50,
        ),  # Doesn't exclude high. This tests the "customizations" idea from easy_infra.yml and functions.j2
        (
            {
                "SKIP_CHECKOV": "true",
                "KICS_EXCLUDE_SEVERITIES": "info,low,medium,high",
            },
            "terraform validate",
            0,
        ),  # Excludes all the severities. This tests the "customizations" idea from easy_infra.yml and functions.j2
    ]

    LOG.debug("Testing terraform with security disabled")
    num_tests_ran += exec_tests(tests=tests, volumes=kics_volumes, image=image)

    # Ensure insecure configurations fail due to checkov
    # Tests is a list of tuples containing the test environment, command, and
    # expected exit code
    tests: list[tuple[dict, str, int]] = [  # type: ignore
        ({}, "terraform --skip-kics plan", 1),
        ({}, "tfenv exec --skip-kics plan", 1),
        (
            {},
            '/usr/bin/env bash -c "SKIP_KICS=true terraform plan"',
            1,
        ),
        (
            {"SKIP_KICS": "true"},
            '/usr/bin/env bash -c "terraform plan || true"',
            0,
        ),
        (
            {},
            '/usr/bin/env bash -c "SKIP_KICS=true terraform plan || true && false"',
            1,
        ),
        (
            {"SKIP_KICS": "true"},
            "terraform --skip-kics plan",
            1,
        ),
        (
            {"LEARNING_MODE": "tRuE", "SKIP_KICS": "TRUE"},
            '/usr/bin/env bash -c "terraform validate"',
            0,
        ),
        (
            {"LEARNING_MODE": "tRuE", "SKIP_KICS": "true"},
            "terraform validate",
            0,
        ),
    ]

    LOG.debug("Testing checkov against insecure terraform")
    num_tests_ran += exec_tests(tests=tests, volumes=checkov_volumes, image=image)

    # Run base interactive terraform tests
    test_interactive_container = CLIENT.containers.run(
        image=image,
        detach=True,
        auto_remove=False,
        tty=True,
        volumes=secure_volumes_with_log_config,
        environment=environment,
    )

    # Running an interactive terraform command
    test_interactive_container.exec_run(
        cmd='/bin/bash -ic "terraform validate"', tty=True
    )

    # An interactive terraform command should not cause the creation of the following files, and should have the same number of logs lines in the
    # fluent bit log regardless of which image is being tested
    files = ["/tmp/kics_complete"]
    files.append("/tmp/checkov_complete")
    LOG.debug("Testing interactive terraform commands")
    number_of_security_tools = len(CONFIG["commands"]["terraform"]["security"])
    expected_number_of_logs = number_of_security_tools

    # Check the container
    if (
        num_successful_tests := check_container(
            container=test_interactive_container,
            files=files,
            files_expected_to_exist=False,
            log_path="/tmp/fluent_bit.log",
            expected_log_length=expected_number_of_logs,
        )
    ) == 0:
        test_interactive_container.kill()
        sys.exit(230)

    test_interactive_container.kill()

    num_tests_ran += num_successful_tests

    # Run secondary interactive terraform tests
    test_interactive_container = CLIENT.containers.run(
        image=image,
        detach=True,
        auto_remove=False,
        tty=True,
        volumes=secure_volumes_with_log_config,
        environment=environment,
    )

    # Running an interactive terraform command
    test_interactive_container.exec_run(
        cmd='/bin/bash -ic "terraform validate"', tty=True
    )

    # An interactive terraform command should still cause the creation of the following files, and should have the same number of logs lines in the
    # fluent bit log regardless of which image is being tested
    files = [str(kics_output_file)]
    files.append(str(checkov_output_file))
    LOG.debug("Testing that interactive terraform commands still create json reports")
    number_of_security_tools = len(CONFIG["commands"]["terraform"]["security"])
    expected_number_of_logs = number_of_security_tools

    # Check the container
    if (
        num_successful_tests := check_container(
            container=test_interactive_container,
            files=files,
            files_expected_to_exist=True,
            log_path="/tmp/fluent_bit.log",
            expected_log_length=expected_number_of_logs,
        )
    ) == 0:
        test_interactive_container.kill()
        sys.exit(230)

    test_interactive_container.kill()

    num_tests_ran += num_successful_tests

    # Run base non-interactive tests for terraform
    test_noninteractive_container = CLIENT.containers.run(
        image=image,
        detach=True,
        auto_remove=False,
        tty=True,
        volumes=secure_volumes_with_log_config,
        environment=environment,
    )

    # Running a non-interactive terraform command
    test_noninteractive_container.exec_run(
        cmd='/bin/bash -c "terraform validate"', tty=False
    )

    # A non-interactive terraform command should cause the creation of the following files, and should have the same number of logs lines in the
    # fluent bit log regardless of which image is being tested
    files = ["/tmp/kics_complete"]
    files.append("/tmp/checkov_complete")
    # Piggyback checking the kics/checkov json reports on the kics/checkov complete file checks
    files.append(str(kics_output_file))
    files.append(str(checkov_output_file))
    LOG.debug("Testing non-interactive terraform commands")
    number_of_security_tools = len(CONFIG["commands"]["terraform"]["security"])
    expected_number_of_logs = number_of_security_tools

    # Check the container
    if (
        num_successful_tests := check_container(
            container=test_noninteractive_container,
            files=files,
            files_expected_to_exist=True,
            log_path="/tmp/fluent_bit.log",
            expected_log_length=expected_number_of_logs,
        )
    ) == 0:
        test_noninteractive_container.kill()
        sys.exit(230)

    test_noninteractive_container.kill()

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


def run_ansible(*, image: str):
    """Run the ansible-playbook tests"""
    num_tests_ran = 0
    working_dir = "/iac/"
    kics_config_dir = TESTS_PATH.joinpath("ansible/tool/kics")
    kics_volumes = {kics_config_dir: {"bind": working_dir, "mode": "rw"}}
    secure_config_dir = TESTS_PATH.joinpath("ansible/general/secure")
    secure_volumes = {secure_config_dir: {"bind": working_dir, "mode": "rw"}}
    secure_volumes_with_log_config = copy.deepcopy(secure_volumes)
    fluent_bit_config_host = TESTS_PATH.joinpath("fluent-bit.outputs.conf")
    fluent_bit_config_container = "/usr/local/etc/fluent-bit/fluent-bit.outputs.conf"
    secure_volumes_with_log_config[fluent_bit_config_host] = {
        "bind": fluent_bit_config_container,
        "mode": "ro",
    }

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
            '/usr/bin/env bash -c "ansible-playbook insecure.yml --check || true"',
            0,
        ),
        (
            {},
            '/usr/bin/env bash -c "SKIP_CHECKOV=true ansible-playbook insecure.yml --check || true && false"',
            1,
        ),  # checkov is purposefully irrelevant for ansible
        (
            {"SKIP_CHECKOV": "true"},
            '/usr/bin/env bash -c "ansible-playbook insecure.yml --check || false"',
            1,
        ),  # checkov is purposefully irrelevant for ansible
        (
            {"SKIP_CHECKOV": "FaLsE", "SKIP_KICS": "Unknown"},
            "ansible-playbook insecure.yml --check",
            50,
        ),  # checkov is purposefully irrelevant for ansible
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
        (
            {"KICS_INCLUDE_QUERIES": "c3b9f7b0-f5a0-49ec-9cbc-f1e346b7274d"},
            "ansible-playbook insecure.yml --check",
            4,
        ),  # Exits with 4 because insecure.yml is not a valid Play, and the provided insecure playbook does not apply to the included queries.
        # This tests the "customizations" idea from easy_infra.yml and functions.j2
        (
            {"KICS_INCLUDE_QUERIES": "7dfb316c-a6c2-454d-b8a2-97f147b0c0ff"},
            "ansible-playbook insecure.yml --check",
            50,
        ),  # This tests the "customizations" idea from easy_infra.yml and functions.j2
        (
            {
                "KICS_EXCLUDE_SEVERITIES": "info,low",
            },
            "ansible-playbook insecure.yml --check",
            50,
        ),  # Doesn't exclude high or medium.
        # This tests the "customizations" idea from easy_infra.yml and functions.j2
        (
            {
                "KICS_EXCLUDE_SEVERITIES": "high,medium",
            },
            "ansible-playbook insecure.yml --check",
            4,
        ),  # Excludes all the relevant severities, exits 4 because insecure.yml is not a valid Play.
        # This tests the "customizations" idea from easy_infra.yml and functions.j2
        (
            {},
            '/usr/bin/env bash -c "KICS_EXCLUDE_SEVERITIES=info,low,medium,high ansible-playbook insecure.yml --check"',
            4,
        ),  # Excludes all the severities, exits 4 because insecure.yml is not a valid Play.
        # This tests the "customizations" idea from easy_infra.yml and functions.j2
    ]

    num_tests_ran += exec_tests(tests=tests, volumes=kics_volumes, image=image)

    # Run base interactive tests
    test_interactive_container = CLIENT.containers.run(
        image=image,
        detach=True,
        auto_remove=False,
        tty=True,
        volumes=secure_volumes_with_log_config,
    )

    # Running an interactive ansible-playbook command
    test_interactive_container.exec_run(
        cmd='/bin/bash -ic "ansible-playbook secure.yml --check"', tty=True
    )

    # An interactive ansible-playbook command should not cause the creation of
    # the following files, and should have 1 log line in the fluent bit log
    # regardless of which image is being tested
    files = [
        "/tmp/kics_complete",
    ]
    LOG.debug("Testing interactive ansible-playbook commands")
    number_of_security_tools = len(CONFIG["commands"]["ansible"]["security"])
    expected_number_of_logs = number_of_security_tools

    # Check the container
    if (
        num_successful_tests := check_container(
            container=test_interactive_container,
            files=files,
            files_expected_to_exist=False,
            log_path="/tmp/fluent_bit.log",
            expected_log_length=expected_number_of_logs,
        )
    ) == 0:
        test_interactive_container.kill()
        sys.exit(230)

    test_interactive_container.kill()

    num_tests_ran += num_successful_tests

    # Run base non-interactive tests for ansible
    test_noninteractive_container = CLIENT.containers.run(
        image=image,
        detach=True,
        auto_remove=False,
        tty=True,
        volumes=secure_volumes_with_log_config,
    )

    # A non-interactive ansible-playbook command should cause the creation of
    # the following files, and should have 1 log line in the fluent bit log
    # regardless of which image is being tested
    test_noninteractive_container.exec_run(
        cmd='/bin/bash -c "ansible-playbook secure.yml --check"', tty=False
    )
    files = [
        "/tmp/kics_complete",
    ]
    LOG.debug("Testing non-interactive ansible-playbook commands")
    number_of_security_tools = len(CONFIG["commands"]["ansible"]["security"])
    expected_number_of_logs = number_of_security_tools

    # Check the container
    if (
        num_successful_tests := check_container(
            container=test_noninteractive_container,
            files=files,
            files_expected_to_exist=True,
            log_path="/tmp/fluent_bit.log",
            expected_log_length=expected_number_of_logs,
        )
    ) == 0:
        test_noninteractive_container.kill()
        sys.exit(230)

    test_noninteractive_container.kill()

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


def run_security(*, image: str, variant: str):
    """Run the security tests"""
    artifact_labels = utils.get_artifact_labels(variant=variant)
    # This assumes that the last element in the list is versioned, if it is a release
    label = artifact_labels[-1]
    sbom_file = Path(f"sbom.{label}.json")

    if not sbom_file:
        LOG.error(
            f"{sbom_file} was not found; security scans require an SBOM. Please run `pipenv run invoke sbom`"
        )

    # Run a vulnerability scan on the provided SBOM (derived from variant)
    try:
        LOG.info(f"Running a vulnerability scan on {sbom_file}...")
        subprocess.run(
            [
                "grype",
                f"sbom:{str(sbom_file)}",
                "--output",
                "json",
                "--file",
                f"vulns.{label}.json",
            ],
            capture_output=True,
            check=True,
        )
    except subprocess.CalledProcessError as error:
        LOG.error(
            f"stdout: {error.stdout.decode('utf-8')}, stderr: {error.stderr.decode('utf-8')}"
        )
        sys.exit(1)

    LOG.info("%s passed the security tests", image)
