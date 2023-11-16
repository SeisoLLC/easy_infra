#!/usr/bin/env python3
"""
Test Functions
"""

import copy
import os
import re
import shutil
import subprocess
import sys
import time
from logging import getLogger
from pathlib import Path
from typing import Optional, Union

import docker

from easy_infra import constants, utils

# Globals
CWD = Path().absolute()
TESTS_PATH = CWD.joinpath("tests")

LOG = getLogger(__name__)

CLIENT = docker.from_env()


def global_tests(*, tool: str, environment: str, user: str) -> None:
    """Global tests"""
    image_and_tag: str = utils.get_image_and_tag(tool=tool, environment=environment)

    va_num_tests_ran: int = test_version_arguments(
        image=image_and_tag, tool=tool, environment=environment, user=user
    )
    LOG.info(f"{image_and_tag} passed {va_num_tests_ran} integration tests as {user}")

    ts_num_tests_ran: int = test_sh(image=image_and_tag, user=user)
    LOG.info(f"{image_and_tag} passed {ts_num_tests_ran} filesystem tests as {user}")


def test_sh(*, image: str, user: str) -> int:
    """Run test.sh"""
    num_tests_ran: int = 0
    working_dir: str = "/iac/"
    tests_test_dir: Path = TESTS_PATH
    tests_volumes: dict[Path, dict[str, str]] = {
        tests_test_dir: {"bind": working_dir, "mode": "ro"}
    }

    command: str = "./test.sh"
    LOG.debug(f"Running test.sh as {user}")
    utils.opinionated_docker_run(
        image=image,
        volumes=tests_volumes,
        command=command,
        user=user,
        expected_exit=0,
    )
    num_tests_ran += 1
    return num_tests_ran


def test_version_arguments(
    *, image: str, tool: str, environment: str, user: str
) -> int:
    """Given a specific image, test the appropriate version arguments from the config"""
    working_dir: str = "/iac/"
    tests_path: Path = constants.CWD.joinpath("tests")
    volumes: dict[Path, dict[str, str]] = {
        tests_path: {"bind": working_dir, "mode": "ro"}
    }

    num_tests_ran: int = 0

    tools_to_environments: dict[
        str, dict[str, list[str]]
    ] = utils.gather_tools_and_environments(tool=tool, environment=environment)

    # Find the package name for the provided tool
    package_for_tool: str = utils.get_package_name(tool=tool)

    # Assemble the packages to test starting with the environment packages
    packages_to_test: list[str] = []
    for env in tools_to_environments[tool]["environments"]:
        for env_package in constants.CONFIG["environments"][env]["packages"]:
            packages_to_test.append(env_package)

    # Populate a list of version commands to test
    for package in constants.CONFIG["packages"]:
        # Ignore already identified packages
        if package in packages_to_test:
            LOG.debug(f"{package} is already on the list to test, not re-adding it...")
            continue

        # In order to test it, we need a version_argument set
        if "version_argument" not in constants.CONFIG["packages"][package]:
            LOG.debug(
                f"{tool} does not have a version_argument set, we cannot test it..."
            )
            continue

        # Add tool packages and helper packages
        if (
            # The package is the right package for the given tool
            package == package_for_tool
            # The package is referenced in the security section of the provided tool
            or (
                "security" in constants.CONFIG["packages"][package_for_tool]
                and package
                in constants.CONFIG["packages"][package_for_tool]["security"]
            )
            # The package "help"s the provided tool
            or (
                "helper" in constants.CONFIG["packages"][package]
                and set(constants.CONFIG["packages"][package]["helper"]).intersection(
                    {tool, package_for_tool, "all"}
                )
            )
        ):
            packages_to_test.append(package)
            continue

    commands_to_test: set[str] = set()
    for package in packages_to_test:
        if "aliases" in constants.CONFIG["packages"][package]:
            for alias in constants.CONFIG["packages"][package]["aliases"]:
                commands_to_test.add(
                    f'command {alias} {constants.CONFIG["packages"][package]["version_argument"]}'
                )
        else:
            commands_to_test.add(
                f'command {package} {constants.CONFIG["packages"][package]["version_argument"]}'
            )

    LOG.debug(
        f"Testing the following commands for image {image} as {user}: {commands_to_test}..."
    )
    for command in commands_to_test:
        utils.opinionated_docker_run(
            image=image,
            volumes=volumes,
            working_dir=working_dir,
            command=command,
            user=user,
            expected_exit=0,
        )
        num_tests_ran += 1

    return num_tests_ran


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
                LOG.error(f"Didn't find the file {file} when it was expected")
            elif not expected_to_exist:
                LOG.error(f"Found the file {file} when it was not expected")
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
    Compare the number of lines in the provided file_path to the provided expected length, in the provided container.
    Return True if the file length is expected, else False
    """
    exit_code, output = container.exec_run(
        cmd=f"/bin/bash -c \"set -o pipefail; wc -l {log_path} | awk '{{print $1}}'\""
    )
    sanitized_output: int = int(output.decode("utf-8").strip())
    if exit_code != 0:
        LOG.error(f"The provided container exited with an exit code of {exit_code}")
        return False

    if sanitized_output != expected_log_length:
        LOG.error(
            f"The file {log_path} had a length of {sanitized_output} when a length of {expected_log_length} was expected",
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
        # Give fluent-bit enough time to dequeue to the output file
        time.sleep(1)

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


def run_path_check(
    *, tool: str, user: str, environment: Optional[str] = None, image_and_tag: str
) -> None:
    """Wrapper to run check_paths"""
    commands: list[str] = []

    for package in constants.CONFIG["packages"]:
        if (
            # If it's the tool package
            package == tool
            # Or if it's a security tool for tool
            or (
                tool in constants.CONFIG["packages"]
                and package in constants.CONFIG["packages"][tool]["security"]
            )
            # Or if the tool is a custom name
            or (
                "tool" in constants.CONFIG["packages"][package]
                and "name" in constants.CONFIG["packages"][package]["tool"]
                and package == constants.CONFIG["packages"][package]["tool"]["name"]
            )
            # Or if it's an applicable helper
            or (
                "helper" in constants.CONFIG["packages"][package]
                and set(constants.CONFIG["packages"][package]["helper"]).intersection(
                    {tool, "all"}
                )
            )
            # Or if it's a tool for the specified environment
            or (
                environment
                and environment in constants.ENVIRONMENTS
                and package in constants.CONFIG["environments"][environment]["packages"]
            )
        ):
            if "aliases" in constants.CONFIG["packages"][package]:
                commands += constants.CONFIG["packages"][package]["aliases"]
            else:
                commands.append(package)

    for interactive in [True, False]:
        num_successful_tests: int = check_paths(
            interactive=interactive,
            user=user,
            commands=commands,
            image_and_tag=image_and_tag,
        )

        if num_successful_tests > 0:
            context: str = "interactive" if interactive else "non-interactive"
            LOG.info(
                f"{image_and_tag} passed all {num_successful_tests} {context} path tests with user {user}"
            )
        else:
            context: str = "an interactive" if interactive else "a non-interactive"
            LOG.error(f"{image_and_tag} failed {context} path test with user {user}")
            sys.exit(1)


def check_paths(
    *,
    interactive: bool,
    user: str,
    commands: list[str],
    image_and_tag: str,
) -> int:
    """
    Check the commands in easy_infra.yml to ensure they are in the supported user's PATH.
    Return 0 for any failures, or the number of correctly found files
    """
    # All commands should be in the PATH of supported users
    num_successful_tests: int = 0
    container = CLIENT.containers.run(
        image=image_and_tag,
        detach=True,
        user=user,
        auto_remove=False,
        tty=True,
    )

    LOG.debug(f"Testing the {user} user's PATH when interactive is {interactive}")
    for command in commands:
        if interactive:
            attempt = container.exec_run(
                cmd=f'/bin/bash -ic "which {command}"', tty=True
            )
        else:
            attempt = container.exec_run(
                cmd=f'/bin/bash -c "which {command}"',
            )
        if attempt[0] != 0:
            LOG.error(f"{command} is not in the PATH of {user} in {image_and_tag}")
            container.kill()
            return 0

        num_successful_tests += 1
    container.kill()
    return num_successful_tests


def exec_tests(
    *,
    image: str,
    tests: list[tuple[dict, str, int]],
    user: str = "",
    volumes: dict | list[dict],
    network_mode: Union[str, None] = None,
) -> int:
    """Execute the provided tests and return a count of tests run"""
    num_tests_ran = 0
    if isinstance(volumes, dict):
        config_dir = list(volumes.keys())[0]
        working_dir = volumes[config_dir]["bind"]
        final_volumes: dict = volumes
    elif isinstance(volumes, list):
        # Use the first dict in the list to extract working dir, etc.
        config_dir = list(volumes[0].keys())[0]
        working_dir = volumes[0][config_dir]["bind"]
        final_volumes: list[str] = []
        for volume in volumes:
            for k, v in volume.items():
                final_volumes.append(str(k.absolute()) + ":" + v["bind"])

    if not user:
        LOG.error("A user must be specified to execute tests!")
        sys.exit(1)

    for environment, command, expected_exit in tests:
        LOG.debug(f"{environment=}, {command=}, {expected_exit=}")
        utils.opinionated_docker_run(
            command=command,
            environment=environment,
            expected_exit=expected_exit,
            image=image,
            user=user,
            volumes=final_volumes,
            working_dir=working_dir,
            network_mode=network_mode,
        )
        num_tests_ran += 1
    return num_tests_ran


def run_tests(
    *,
    image: str,
    user: str,
    tool: str,
    environment: Optional[str],
    mount_local_files: bool = False,
) -> None:
    """Fanout function to run the appropriate tests"""
    if mount_local_files:
        # Render with the full, unfiltered config
        utils.render_jinja2(
            template_file=constants.FUNCTIONS_INPUT_FILE,
            config=constants.CONFIG,
            output_file=constants.FUNCTIONS_OUTPUT_FILE,
            output_mode=0o755,
        )

    run_path_check(tool=tool, user=user, environment=environment, image_and_tag=image)

    tool_test_function: str = f"run_{tool}"
    eval(tool_test_function)(
        image=image,
        user=user,
        mount_local_files=mount_local_files,
    )  # nosec B307 pylint: disable=eval-used

    if environment and environment != "none":
        environment_test_function: str = f"run_{environment}"
        # TODO: Consider how we may want to test {tool}-{environment} features specifically; right now it is environment-only testing
        eval(environment_test_function)(  # nosec B307 pylint: disable=eval-used
            image=image,
            user=user,
            mount_local_files=mount_local_files,
        )
        tag: str = constants.CONTEXT[tool][environment]["versioned_tag"]
    else:
        tag: str = constants.CONTEXT[tool]["versioned_tag"]

    # TODO: Fix typing issue here with environment; None vs str
    global_tests(tool=tool, environment=environment, user=user)
    # No need to supply a user to the security scans as they are container-global
    run_security(tool=tool, environment=environment, tag=tag)

    if os.getenv("GITHUB_ACTIONS") != "true":
        return

    # See the warning under https://docs.python.org/3/library/subprocess.html#popen-constructor and some additional context in
    # https://github.com/python/cpython/issues/105889
    if (task_absolute_path := shutil.which("task")) is None:
        LOG.error("Unable to find task in your PATH")
        sys.exit(1)

    # Cleanup after test runs in a pipeline
    try:
        env: dict[str, str] = os.environ.copy()
        LOG.debug(f"{env=}")
        # https://unix.stackexchange.com/a/83194/28597 and https://manpages.ubuntu.com/manpages/focal/en/man8/sudo.8.html#environment are good
        # references
        command: str = f"sudo env PATH='{env['PATH']}' {task_absolute_path} -v clean"
        out = subprocess.run(
            command,
            capture_output=True,
            check=True,
            shell=True,
        )
        LOG.debug(
            f"stdout: {out.stdout.decode('UTF-8')}, stderr: {out.stderr.decode('UTF-8')}"
        )
    except subprocess.CalledProcessError as error:
        LOG.error(
            f"stdout: {error.stdout.decode('UTF-8')}, stderr: {error.stderr.decode('UTF-8')}"
        )
        sys.exit(1)


def run_cloudformation(*, image: str, user: str, mount_local_files: bool) -> None:
    """Run the CloudFormation tests"""
    num_tests_ran: int = 0
    working_dir: str = "/iac/"
    environment: dict[str, str] = {"AWS_DEFAULT_REGION": "ap-northeast-1"}
    cloudformation_test_dir: Path = TESTS_PATH.joinpath("cloudformation")
    volumes: list[dict[Path, dict[str, str]]] = []
    secure_test_dir: Path = cloudformation_test_dir.joinpath("general/secure")
    secure_volumes: dict[Path, dict[str, str]] = {
        secure_test_dir: {"bind": working_dir, "mode": "rw"}
    }
    volumes.append(secure_volumes)
    alt_working_dir: str = "/alt_working_dir/"
    alt_bind_secure_volumes = copy.deepcopy(secure_volumes)
    alt_bind_secure_volumes[secure_test_dir]["bind"] = alt_working_dir
    volumes.append(alt_bind_secure_volumes)
    checkov_test_dir: Path = cloudformation_test_dir.joinpath("tool/checkov")
    checkov_volumes: dict[Path, dict[str, str]] = {
        checkov_test_dir: {"bind": working_dir, "mode": "rw"}
    }
    volumes.append(checkov_volumes)
    fluent_bit_config_host: Path = TESTS_PATH.joinpath("fluent-bit.outputs.conf")
    fluent_bit_config_container: str = (
        "/usr/local/etc/fluent-bit/fluent-bit.outputs.conf"
    )
    secure_volumes_with_log_config: dict[Path, dict[str, str]] = copy.deepcopy(
        secure_volumes
    )
    secure_volumes_with_log_config[fluent_bit_config_host] = {
        "bind": fluent_bit_config_container,
        "mode": "ro",
    }
    volumes.append(secure_volumes_with_log_config)
    # This is for use inside of the container
    report_base_dir: Path = Path("/tmp/reports")
    checkov_output_file: Path = report_base_dir.joinpath("checkov").joinpath(
        "checkov.json"
    )
    if mount_local_files:
        functions_dir = CWD.joinpath("build").joinpath("functions.sh")
        common_dir = CWD.joinpath("build").joinpath("common.sh")
        for volume in volumes:
            volume[functions_dir] = {"bind": "/functions.sh"}
            volume[common_dir] = {"bind": "/usr/local/bin/common.sh"}

    # Test alternative working directories/binds
    # Tests is a list of tuples containing the test environment, command, and expected exit code
    tests: list[tuple[dict, str, int]] = [  # type: ignore
        (
            {"AWS_DEFAULT_REGION": "ap-northeast-1"},
            "aws cloudformation validate-template --template-body file://./secure.yml",
            253,
        ),
        ({}, "scan_cloudformation", 0),
    ]

    LOG.debug("Testing alternative working dirs/binds with the cloudformation image")
    num_tests_ran += exec_tests(
        tests=tests, volumes=alt_bind_secure_volumes, image=image, user=user
    )

    # Ensure secure configurations pass
    # Tests is a list of tuples containing the test environment, command, and expected exit code
    tests: list[tuple[dict, str, int]] = [  # type: ignore
        (
            {"AWS_DEFAULT_REGION": "ap-northeast-1"},
            "aws cloudformation validate-template --template-body file://./secure.yml",
            253,
        ),  # Unfortunately you need to provide creds to make this succeed, as it actually deploys the resources by design by AWS.
        #     So we are testing for exit 253 which is what happens when the aws command isn't able to identify credentials, which is a weak way to
        #     test that it passes the security scans. More details in:
        #     https://www.linkedin.com/posts/jonzeolla_aws-iac-infrastructureascode-activity-7049057908302471168-WMqJ
        #     https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-validate-template.html
        ({}, "scan_cloudformation", 0),
        (
            {},
            '/bin/bash -c "aws --version; scan_cloudformation"',
            0,
        ),
        (
            {"CHECKOV_SKIP_CHECK": "CKV_AWS_20"},
            "scan_cloudformation",
            0,
        ),  # This tests "arg_customizations" features from easy_infra.yml and functions.j2
        # TODO: Test env_customizations
    ]

    LOG.debug("Testing secure cloudformation templates")
    num_tests_ran += exec_tests(
        tests=tests, volumes=secure_volumes, image=image, user=user
    )

    # Ensure insecure configurations still succeed when security checks are disabled
    # Tests is a list of tuples containing the test environment, command, and expected exit code
    tests: list[tuple[dict, str, int]] = [  # type: ignore
        (
            {"AWS_DEFAULT_REGION": "ap-northeast-1", "DISABLE_SECURITY": "true"},
            "aws cloudformation validate-template --template-body file://./insecure.yml",
            253,
        ),  # See above exit 253 comments
        (
            {"AWS_DEFAULT_REGION": "ap-northeast-1"},
            "aws cloudformation --disable-security validate-template --template-body file://./insecure.yml",
            253,
        ),  # See above exit 253 comments
        (
            {"AWS_DEFAULT_REGION": "ap-northeast-1"},
            "aws cloudformation validate-template --template-body file://./insecure.yml --disable-security",
            253,
        ),  # See above exit 253 comments
        ({"DISABLE_SECURITY": "true"}, "scan_cloudformation", 0),
        ({}, '/usr/bin/env bash -c "DISABLE_SECURITY=true scan_cloudformation"', 0),
        ({}, "scan_cloudformation --disable-security", 0),
        (
            {},
            '/usr/bin/env bash -c "DISABLE_SECURITY=true scan_cloudformation --disable-security"',
            0,
        ),
        (
            {},
            '/usr/bin/env bash -c "DISABLE_SECURITY=true scan_cloudformation --disable-security && false"',
            1,
        ),
        (
            {
                "CHECKOV_SKIP_CHECK": "CKV_AWS_53",  # Would normally still fail due to numerous other rules (currently 33)
                "DISABLE_SECURITY": "true",
            },
            "scan_cloudformation",
            0,
        ),  # This tests the "arg_customizations" idea from easy_infra.yml and functions.j2
        # TODO: Test env_customizations
    ]

    LOG.debug("Testing scan_cloudformation with security disabled")
    num_tests_ran += exec_tests(
        tests=tests, volumes=checkov_volumes, image=image, user=user
    )

    # Ensure insecure configurations fail properly due to checkov
    # Tests is a list of tuples containing the test environment, command, and expected exit code
    tests: list[tuple[dict, str, int]] = [  # type: ignore
        (
            {},
            "aws cloudformation validate-template --template-body file://./insecure.yml",
            1,
        ),
        (
            {"AWS_DEFAULT_REGION": "ap-northeast-1", "LEARNING_MODE": "TRUE"},
            "aws cloudformation validate-template --template-body file://./insecure.yml",
            253,
        ),  # See above exit 253 comments
        ({}, "scan_cloudformation", 1),
        (
            {},
            '/usr/bin/env bash -c "scan_cloudformation"',
            1,
        ),
        (
            {},
            '/usr/bin/env bash -c "scan_cloudformation || true"',
            0,
        ),
        (
            {"LEARNING_MODE": "tRuE"},
            '/usr/bin/env bash -c "scan_cloudformation"',
            0,
        ),
        (
            {"LEARNING_MODE": "tRuE"},
            "scan_cloudformation",
            0,
        ),
    ]

    LOG.debug("Testing checkov against insecure cloudformation templates")
    num_tests_ran += exec_tests(
        tests=tests, volumes=checkov_volumes, image=image, user=user
    )

    # Run base non-interactive tests for cloudformation
    test_noninteractive_container = CLIENT.containers.run(
        image=image,
        detach=True,
        auto_remove=False,
        tty=True,
        volumes=secure_volumes_with_log_config,
        environment=environment,
    )

    # Running a non-interactive scan_cloudformation
    test_noninteractive_container.exec_run(
        cmd='/bin/bash -c "aws cloudformation validate-template --template-body file://./insecure.yml"',
        tty=False,
    )

    # A non-interactive aws cloudformation command should cause the creation of the following files, and should have the same number of logs lines in the
    # fluent bit log regardless of which image is being tested
    files = ["/tmp/checkov_complete"]
    # Piggyback checking the checkov reports on the checkov complete file checks
    files.append(str(checkov_output_file))
    LOG.debug("Testing non-interactive aws cloudformation command")
    # The package name for cloudformation is aws-cli
    number_of_security_tools: int = len(
        constants.CONFIG["packages"]["aws-cli"]["security"]
    )
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

    # Run scan_cloudformation version non-interactive test
    test_noninteractive_container = CLIENT.containers.run(
        image=image,
        detach=True,
        auto_remove=False,
        tty=True,
        volumes=secure_volumes,
        environment=environment,
    )

    # Running a non-interactive scan_cloudformation version (or any other supported "version" argument) should NOT cause the creation of the following
    # files
    test_noninteractive_container.exec_run(
        cmd='/bin/bash -c "scan_cloudformation version"', tty=False
    )
    files = ["/tmp/checkov_complete"]
    LOG.debug("Testing non-interactive scan_cloudformation version")
    if (
        num_successful_tests := check_for_files(
            container=test_noninteractive_container,
            files=files,
            expected_to_exist=False,
        )
    ) == 0:
        test_noninteractive_container.kill()
        sys.exit(1)

    test_noninteractive_container.kill()

    num_tests_ran += num_successful_tests

    LOG.info(f"{image} passed {num_tests_ran} end to end cloudformation tests")


def run_unified_terraform_opentofu(*, image: str, user: str, base_command: str, mount_local_files: bool) -> None:
    """Run the unified terraform and opentofu tests"""
    key = base_command if base_command == "terraform" else "opentofu"
    num_tests_ran: int = 0
    working_dir: str = "/iac/"
    environment: dict[str, str] = {"TF_DATA_DIR": "/tmp"}
    volumes: list[dict[Path, dict[str, str]]] = []
    terraform_test_dir: Path = TESTS_PATH.joinpath("terraform")
    invalid_test_dir: Path = terraform_test_dir.joinpath("general/invalid")
    invalid_volumes: dict[Path, dict[str, str]] = {
        invalid_test_dir: {"bind": working_dir, "mode": "rw"}
    }
    volumes.append(invalid_volumes)
    checkov_test_dir: Path = terraform_test_dir.joinpath("tool/checkov")
    checkov_volumes: dict[Path, dict[str, str]] = {
        checkov_test_dir: {"bind": working_dir, "mode": "rw"}
    }
    volumes.append(checkov_volumes)
    large_checkov_output_file: Path = terraform_test_dir.joinpath("checkov.json")
    large_checkov_volumes: dict[Path, dict[str, str]] = {
        large_checkov_output_file: {
            "bind": "/tmp/reports/checkov/checkov.json",
            "mode": "ro",
        }
    }
    volumes.append(large_checkov_volumes)
    secure_config_dir: Path = terraform_test_dir.joinpath("general/secure")
    secure_volumes: dict[Path, dict[str, str]] = {
        secure_config_dir: {"bind": working_dir, "mode": "rw"}
    }
    volumes.append(secure_volumes)
    alt_working_dir: str = "/alt_working_dir/"
    alt_bind_secure_volumes = copy.deepcopy(secure_volumes)
    alt_bind_secure_volumes[secure_config_dir]["bind"] = alt_working_dir
    volumes.append(alt_bind_secure_volumes)
    general_test_dir: Path = terraform_test_dir.joinpath("general")
    general_test_volumes: dict[Path, dict[str, str]] = {
        general_test_dir: {"bind": working_dir, "mode": "rw"}
    }
    volumes.append(general_test_volumes)
    hooks_config_dir: Path = terraform_test_dir.joinpath("hooks")
    hooks_config_volumes: dict[Path, dict[str, str]] = {
        hooks_config_dir: {"bind": working_dir, "mode": "rw"}
    }
    volumes.append(hooks_config_volumes)
    hooks_script_dir: Path = TESTS_PATH.joinpath("test-hooks")
    hooks_script_volumes: dict[Path, dict[str, str]] = {
        hooks_script_dir: {"bind": "/opt/hooks/bin/", "mode": "ro"}
    }
    volumes.append(hooks_script_volumes)
    fluent_bit_config_host: Path = TESTS_PATH.joinpath("fluent-bit.outputs.conf")
    fluent_bit_config_container: str = (
        "/usr/local/etc/fluent-bit/fluent-bit.outputs.conf"
    )
    secure_volumes_with_log_config: dict[Path, dict[str, str]] = copy.deepcopy(
        secure_volumes
    )
    secure_volumes_with_log_config[fluent_bit_config_host] = {
        "bind": fluent_bit_config_container,
        "mode": "ro",
    }
    volumes.append(secure_volumes_with_log_config)
    report_base_dir: Path = Path("/tmp/reports")
    checkov_output_file: Path = report_base_dir.joinpath("checkov").joinpath(
        "checkov.json"
    )
    if mount_local_files:
        functions_dir = CWD.joinpath("build").joinpath("functions.sh")
        common_dir = CWD.joinpath("build").joinpath("common.sh")
        for volume in volumes:
            volume[functions_dir] = {"bind": "/functions.sh"}
            volume[common_dir] = {"bind": "/usr/local/bin/common.sh"}

    # Ensure invalid configurations fail
    command: str = f"{base_command} init"
    LOG.debug(f"Testing invalid {base_command} configurations")
    utils.opinionated_docker_run(
        image=image,
        volumes=invalid_volumes,
        command=command,
        environment=environment,
        expected_exit=1,
    )
    num_tests_ran += 1

    # Test learning mode on an invalid configuration, using the git clone feature, non-interactively
    #
    # Note that we can't just replace the cd with workdir because it will create the dir as root prior to hitting the ENTRYPOINT, and the container
    # user won't have access to write in that directory when it tries to run _clone. This was fixed in buildkit in
    # https://github.com/moby/buildkit/pull/1002 but docker-py doesn't support buildkit yet; see the very popular
    # https://github.com/docker/docker-py/issues/2230 issue from January 2019
    #
    # The exit 230 ensures that, if the dir doesn't exist, it doesn't accidentally match the expected_exit of 1 below
    command = f'/bin/bash -c "cd /iac/seisollc/easy_infra/tests/terraform/general/invalid || exit 230 && {base_command} validate"'
    LOG.debug(
        "Testing learning mode on an invalid configuration using the git clone feature, non-interactively"
    )
    learning_environment = copy.deepcopy(environment)
    learning_environment["LEARNING_MODE"] = "true"
    learning_mode_and_clone_environment = copy.deepcopy(learning_environment)

    # Setup the cloning
    learning_mode_and_clone_environment["VCS_DOMAIN"] = "github.com"
    learning_mode_and_clone_environment[
        "CLONE_REPOSITORIES"
    ] = "seisollc/easy_infra,seisollc/easy_infra"
    learning_mode_and_clone_environment["CLONE_PROTOCOL"] = "https"

    # Purposefully missing volumes= because we are using clone to do it
    utils.opinionated_docker_run(
        image=image,
        command=command,
        environment=learning_mode_and_clone_environment,
        expected_exit=1,  # This still fails the final {base_command} validate, which only runs if scan_{base_command} succeeds as expected
    )
    num_tests_ran += 1

    # Ensure that the logging functions work, even when there are a lot of findings
    command = '_log "test" "denied" "failure" "_log test" "/tmp" "json" "/tmp/reports/checkov/checkov.json"'
    LOG.debug(
        "Test writing easy_infra.log when there are a significant number of findings"
    )
    # If this pattern matches the logs, it will fail the test
    pattern = re.compile(r"ERROR")

    utils.opinionated_docker_run(
        image=image,
        volumes=large_checkov_volumes,
        command=command,
        environment=environment,
        expected_exit=0,
        check_logs=pattern,
    )
    num_tests_ran += 1

    # Ensure autodetect finds the appropriate {base_command} configs, which can be inferred by the number of logs written to /var/log/easy_infra.log
    #
    # This test requires LEARNING_MODE to be true because the autodetect functionality traverses into the testing sub-directories, including those
    # which are purposefully insecure, which otherwise would exit non-zero early, resulting in a limited set of logs.
    # There is always one log for each security tool, regardless of if that tool is installed in the image being used.  If a tool is not in the PATH
    # and executable, a log message indicating that is generated.
    number_of_security_tools = len(constants.CONFIG["packages"][key]["security"])
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
    learning_mode_and_autodetect_environment = copy.deepcopy(learning_environment)
    learning_mode_and_autodetect_environment["DISABLE_HOOKS"] = "true"
    LOG.debug("Testing LEARNING_MODE with various AUTODETECT configurations")

    tests: list[tuple[dict, str, int]] = []
    for index, autodetect_status in enumerate(["true", "false", "true"]):
        fail_fast = "false"
        if autodetect_status == "true":
            if index == 0:
                # Since DISABLE_HOOKS and LEARNING_MODE are true and FAIL_FAST is left to its default, there is:
                # - one log per number_of_testing_dirs saying that hooks are disabled
                # - one log per number_of_security_tools per number_of_testing_dirs for those security tools
                expected_number_of_logs = (
                    number_of_security_tools * number_of_testing_dirs
                    + number_of_testing_dirs
                )
            else:
                # Test FAIL_FAST; since LEARNING_MODE is true, FAIL_FAST is not effective
                fail_fast = "true"

                # Since DISABLE_HOOKS and LEARNING_MODE are true and FAIL_FAST is left to its default, there is:
                # - one log per number_of_testing_dirs saying that hooks are disabled
                # - one log per number_of_security_tools per number_of_testing_dirs for those security tools
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
        command = (
            f'/bin/bash -c "{base_command} init -backend=false && {test_log_length}"'
        )
        learning_mode_and_autodetect_environment["AUTODETECT"] = autodetect_status
        learning_mode_and_autodetect_environment["FAIL_FAST"] = fail_fast
        tests.append(
            (copy.deepcopy(learning_mode_and_autodetect_environment), command, 0)
        )

    # Test FAIL_FAST when autodetect is true but learning_mode is false; the logs should be limited to those expected up until the first encountered
    # failure
    fail_fast_environment = copy.deepcopy(learning_mode_and_autodetect_environment)
    fail_fast_environment["LEARNING_MODE"] = "false"
    fail_fast_environment["FAIL_FAST"] = "true"

    # Use the index of the 'invalid' dir as the expected number of logs, since it fails at invalid. Note that the general_test_dirs list needs to be
    # alphabetically sorted
    invalid_dir_index = general_test_dirs.index(invalid_test_dir)

    # One log for each folder that would be encountered; + 1 to adjust for 0-indexing
    logs_from_disable_hooks = invalid_dir_index + 1
    expected_number_of_logs = (
        invalid_dir_index + 1
    ) * number_of_security_tools + logs_from_disable_hooks

    tests.append((copy.deepcopy(learning_mode_and_autodetect_environment), command, 0))

    num_tests_ran += exec_tests(
        tests=tests, volumes=general_test_volumes, image=image, user=user
    )

    # Ensure autodetect finds the appropriate {base_command} configs, which can be inferred by the number of logs written to /var/log/easy_infra.log
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
        command = f'/bin/bash -c "{base_command} init && {base_command} validate"'

        if autodetect_status == "true":
            # Expect exit 1 due to the discovery of {base_command}/general/invalid/invalid.tf
            expected_exit = 1
        elif autodetect_status == "false":
            # Expect exit 0 because the command is ran in {base_command}/general and doesn't discover subdirs
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
            # Since DISABLE_HOOKS and DISABLE_SECURITY are both true, you should expect 1 log each (2) for each testing directory
            expected_number_of_logs = number_of_testing_dirs + number_of_testing_dirs
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
            cmd=f'/bin/bash -c "{base_command} init"', tty=False
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

    # Test alternative working directories/binds
    # Tests is a list of tuples containing the test environment, command, and expected exit code
    tests: list[tuple[dict, str, int]] = [  # type: ignore
        ({}, f"{base_command} init", 0),
        ({}, "tfenv exec init", 0),
        (
            {},
            f'/usr/bin/env bash -c "{base_command} init && false"',
            1,
        ),
        (
            {},
            '/usr/bin/env bash -c "tfenv exec init && false"',
            1,
        ),
    ]

    LOG.debug(f"Testing alternative working dirs/binds with the {base_command} image")
    num_tests_ran += exec_tests(
        tests=tests, volumes=alt_bind_secure_volumes, image=image, user=user
    )

    # Ensure secure configurations pass
    # Tests is a list of tuples containing the test environment, command, and expected exit code
    tests: list[tuple[dict, str, int]] = [  # type: ignore
        ({}, f"{base_command} init", 0),
        ({}, "tfenv exec init", 0),
        ({}, f"scan_{base_command}", 0),
        ({}, "scan_tfenv", 0),
        (
            {},
            f'/bin/bash -c "{base_command} init && {base_command} validate && echo no | {base_command} apply"',
            1,
        ),  # Previous Getting Started example from the README.md (Minimally modified for automation)
        (
            {},
            f'/bin/bash -c "{base_command} init; {base_command} version"',
            0,
        ),  # Previous {base_command} Caching example from the README.md
        (
            {},
            f'/usr/bin/env bash -c "{base_command} init && {base_command} validate && {base_command} plan && {base_command} validate"',
            0,
        ),
        (
            {},
            f'/usr/bin/env bash -c "{base_command} init && {base_command} validate && false"',
            1,
        ),
        (
            {"CHECKOV_SKIP_CHECK": "CKV_AWS_8"},
            f"{base_command} init",
            0,
        ),  # This tests "arg_customizations" features from easy_infra.yml and functions.j2
        # TODO: Test env_customizations
    ]

    LOG.debug(f"Testing secure {base_command} configurations")
    num_tests_ran += exec_tests(
        tests=tests, volumes=secure_volumes, image=image, user=user
    )

    # Ensure insecure configurations still succeed when security checks are disabled
    # Tests is a list of tuples containing the test environment, command, and expected exit code
    tests: list[tuple[dict, str, int]] = [  # type: ignore
        ({"DISABLE_SECURITY": "true"}, f"{base_command} init", 0),
        ({"DISABLE_SECURITY": "true"}, "tfenv exec init", 0),
        ({"DISABLE_SECURITY": "true"}, f"scan_{base_command}", 0),
        ({}, f'/usr/bin/env bash -c "DISABLE_SECURITY=true {base_command} init"', 0),
        (
            {},
            f'/usr/bin/env bash -c "DISABLE_SECURITY=true {base_command} --disable-security init"',
            0,
        ),
        ({}, f"{base_command} --disable-security init", 0),  # Test order independence
        ({}, f"{base_command} init --disable-security", 0),  # Test order independence
        (
            {},
            f'/usr/bin/env bash -c "DISABLE_SECURITY=true {base_command} init --disable-security || true && false"',
            1,
        ),
        (
            {"DISABLE_SECURITY": "true"},
            f"{base_command} init || false",
            1,
        ),  # Not supported; reproduce "Too many command line arguments. Configuration path expected." error
        #     locally with `docker run -e DISABLE_SECURITY=true -v $(pwd)/tests/terraform/tool/checkov:/iac seiso/easy_infra:latest-{base_command}
        #     {base_command} plan \|\| false`, prefer passing the commands through bash like the following test
        (
            {},
            f"DISABLE_SECURITY=true {base_command} plan",
            127,
        ),  # Not supported; prepended variables do not work unless the
        #     commands are passed through bash
        (
            {
                "CHECKOV_SKIP_CHECK": "CKV_AWS_8",  # Would normally still fail due to checkov_volumes CKV_AWS_79
                "DISABLE_SECURITY": "true",
            },
            f"{base_command} init",
            0,
        ),  # This tests the "arg_customizations" idea from easy_infra.yml and functions.j2
        # TODO: Test env_customizations
    ]

    LOG.debug(f"Testing {base_command} with security disabled")
    num_tests_ran += exec_tests(
        tests=tests, volumes=checkov_volumes, image=image, user=user
    )

    # Ensure insecure configurations fail properly due to checkov
    # Tests is a list of tuples containing the test environment, command, and expected exit code
    tests: list[tuple[dict, str, int]] = [  # type: ignore
        ({}, f"{base_command} init", 1),
        ({}, "tfenv exec plan", 1),
        ({}, f"scan_{base_command}", 1),
        (
            {},
            f'/usr/bin/env bash -c "{base_command} init"',
            1,
        ),
        (
            {},
            f'/usr/bin/env bash -c "{base_command} init || true"',
            0,
        ),
        (
            {},
            f'/usr/bin/env bash -c "{base_command} init || true && false"',
            1,
        ),
        (
            {"LEARNING_MODE": "tRuE"},
            f'/usr/bin/env bash -c "{base_command} init && {base_command} validate"',
            0,
        ),
        (
            {"LEARNING_MODE": "tRuE"},
            f'/bin/bash -c "{base_command} init && {base_command} validate"',
            0,
        ),
    ]

    LOG.debug(f"Testing checkov against insecure {base_command}")
    num_tests_ran += exec_tests(
        tests=tests, volumes=checkov_volumes, image=image, user=user
    )

    # Run base non-interactive tests for {base_command}
    test_noninteractive_container = CLIENT.containers.run(
        image=image,
        detach=True,
        auto_remove=False,
        tty=True,
        volumes=secure_volumes_with_log_config,
        environment=environment,
    )

    # Running a non-interactive {base_command} command
    test_noninteractive_container.exec_run(
        cmd=f'/bin/bash -c "{base_command} init"', tty=False
    )

    # A non-interactive {base_command} command should cause the creation of the following files, and should have the same number of logs lines in the
    # fluent bit log regardless of which image is being tested
    files = ["/tmp/checkov_complete"]
    # Piggyback checking the checkov reports on the checkov complete file checks
    files.append(str(checkov_output_file))
    LOG.debug(f"Testing non-interactive {base_command} commands")
    number_of_security_tools = len(constants.CONFIG["packages"][key]["security"])
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

    # Run {base_command} version non-interactive test
    test_noninteractive_container = CLIENT.containers.run(
        image=image,
        detach=True,
        auto_remove=False,
        tty=True,
        volumes=secure_volumes,
        environment=environment,
    )

    # Running a non-interactive {base_command} version (or any other supported
    # "version" argument) should NOT cause the creation of the following files
    test_noninteractive_container.exec_run(
        cmd=f'/bin/bash -c "{base_command} version"', tty=False
    )
    files = ["/tmp/checkov_complete"]
    LOG.debug(f"Testing non-interactive {base_command} version")
    if (
        num_successful_tests := check_for_files(
            container=test_noninteractive_container,
            files=files,
            expected_to_exist=False,
        )
    ) == 0:
        sys.exit(1)

    num_tests_ran += num_successful_tests

    LOG.info(f"{image} passed {num_tests_ran} end to end {base_command} tests")


def run_opentofu(*, image: str, user: str, mount_local_files: bool) -> None:
    """Run the opentofu tests"""
    run_unified_terraform_opentofu(image=image, user=user, base_command="tofu", mount_local_files=mount_local_files)


def run_terraform(*, image: str, user: str, mount_local_files: bool) -> None:
    """Run the terraform tests"""
    base_command = "terraform"
    uppercase_base_command = base_command.upper()
    run_unified_terraform_opentofu(image=image, user=user, base_command=base_command, mount_local_files=mount_local_files)

    num_tests_ran: int = 0
    volumes: list[dict[Path, dict[str, str]]] = []
    working_dir: str = "/iac/"
    terraform_test_dir: Path = TESTS_PATH.joinpath("terraform")
    hooks_config_dir: Path = terraform_test_dir.joinpath("hooks")
    hooks_config_volumes: dict[Path, dict[str, str]] = {
        hooks_config_dir: {"bind": working_dir, "mode": "rw"}
    }
    volumes.append(hooks_config_volumes)
    hooks_script_dir: Path = TESTS_PATH.joinpath("test-hooks")
    hooks_script_volumes: dict[Path, dict[str, str]] = {
        hooks_script_dir: {"bind": "/opt/hooks/bin/", "mode": "ro"}
    }
    volumes.append(hooks_script_volumes)
    hooks_secure_terraform_v_builtin_dir: Path = TESTS_PATH.joinpath(
        "terraform/hooks/secure_builtin_version"
    )
    hooks_secure_terraform_v_builtin_dir_volumes: dict[Path, dict[str, str]] = {
        hooks_secure_terraform_v_builtin_dir: {"bind": working_dir, "mode": "rw"}
    }
    volumes.append(hooks_secure_terraform_v_builtin_dir_volumes)
    hooks_secure_terraform_v_0_14_dir: Path = TESTS_PATH.joinpath(
        "terraform/hooks/secure_0_14"
    )
    hooks_secure_terraform_v_0_14_dir_volumes: dict[Path, dict[str, str]] = {
        hooks_secure_terraform_v_0_14_dir: {"bind": working_dir, "mode": "rw"}
    }
    volumes.append(hooks_secure_terraform_v_0_14_dir_volumes)
    
    if mount_local_files:
        functions_dir = CWD.joinpath("build").joinpath("functions.sh")
        common_dir = CWD.joinpath("build").joinpath("common.sh")
        for volume in volumes:
            volume[functions_dir] = {"bind": "/functions.sh"}
            volume[common_dir] = {"bind": "/usr/local/bin/common.sh"}

    # Ensure the easy_infra hooks work as expected when network access is available
    # Tests is a list of tuples containing the test environment, command, and expected exit code
    tests: list[tuple[dict, str, int]] = [  # type: ignore
        (
            {
                "DISABLE_HOOKS": "false",
                "AUTODETECT": "true",
                "DISABLE_SECURITY": "true",
            },
            f'/bin/bash -c "{base_command} init -backend=false && {base_command} validate"',
            0,
        ),  # This tests the {base_command} version switching hook, regardless of the built-in security tools
        (
            {
                "DISABLE_HOOKS": "true",
                "AUTODETECT": "true",
                "DISABLE_SECURITY": "true",
            },
            f'/bin/bash -c "{base_command} init -backend=false && {base_command} validate"',
            1,
        ),  # This tests DISABLE_HOOKS; it fails because the {base_command} version used is incorrect
    ]

    LOG.debug(
        f"Testing the easy_infra hooks against various {base_command} configurations"
    )
    num_tests_ran += exec_tests(
        tests=tests, volumes=hooks_config_volumes, image=image, user=user
    )

    # Ensure the easy_infra hooks work as expected when network access is NOT available
    # Tests is a list of tuples containing the test environment, command, and expected exit code
    tests: list[tuple[dict, str, int]] = [  # type: ignore
        (
            {
                "DISABLE_HOOKS": "false",
                "AUTODETECT": "true",
                "DISABLE_SECURITY": "true",
            },
            f'/bin/bash -c "{base_command} init -backend=false && {base_command} validate"',
            1,
        ),  # This tests the {base_command} version switching hook failback due to no network (see exec_tests below)
        # It fails because terraform/hooks/secure_0_14/secure.tf cannot be validated with the version of {base_command}
        # that {uppercase_base_command}_VERSION indicates by default
    ]
    LOG.debug(
        f"Testing the easy_infra hooks with no network access, against various {base_command} configurations, expecting failures"
    )
    num_tests_ran += exec_tests(
        tests=tests,
        volumes=hooks_config_volumes,
        image=image,
        user=user,
        network_mode="none",
    )

    # Ensure the scan_ hooks work and that you can provide custom hooks via volume mounting at runtime
    # Tests is a list of tuples containing the test environment, command, and expected exit code
    tests: list[tuple[dict, str, int]] = [  # type: ignore
        (
            {"DISABLE_SECURITY": "true"},
            f"scan_{base_command}",
            230,
        )  # This tests scan_{base_command} hook registration; if it runs and finds the unwanted file it should exit 230
    ]

    LOG.debug("Testing scan_ hooks and custom hooks volume mounted at runtime")
    volumes: list[dict[Path, dict[str, str]]] = [
        hooks_config_volumes,
        hooks_script_volumes,
    ]
    num_tests_ran += exec_tests(tests=tests, volumes=volumes, image=image, user=user)

    # Ensure the easy_infra hooks honor Learning Mode by not failing on hook script errors
    # Tests is a list of tuples containing the test environment, command, and expected exit code
    tests: list[tuple[dict, str, int]] = [  # type: ignore
        (
            {
                "DISABLE_HOOKS": "false",
                "DISABLE_SECURITY": "true",
                "FAIL_FAST": "true",
                "LEARNING_MODE": "true",
            },
            f'/bin/bash -c "scan_{base_command}"',
            0,
        ),  # This tests that the failed script does not fail easy_infra when LM is enabled
        (
            {
                "DISABLE_HOOKS": "false",
                "DISABLE_SECURITY": "true",
                "FAIL_FAST": "true",
                "LEARNING_MODE": "false",
            },
            f'/bin/bash -c "scan_{base_command}"',
            230,
        ),  # This tests the hook script for a non-zero exit code that would result in easy_infra failing when LM is disabled
        (
            {
                "DISABLE_HOOKS": "false",
                "DISABLE_SECURITY": "true",
                "FAIL_FAST": "false",
                "LEARNING_MODE": "false",
            },
            f'/bin/bash -c "scan_{base_command}"',
            230,
        ),  # This tests the hook script for a non-zero exit code with FAIL_FAST and LEARNING_MODE both disabled to ensure the
        # failed hook gets added to the dir_exit_codes array
    ]

    LOG.debug("Testing Learning Mode for custom hooks volume mounted at runtime")
    num_tests_ran += exec_tests(
        tests=tests, volumes=hooks_script_volumes, image=image, user=user
    )

    tests: list[tuple[dict, str, int]] = [  # type: ignore
        (
            {
                "DISABLE_HOOKS": "false",
                "AUTODETECT": "false",
                "DISABLE_SECURITY": "true",
                f"{uppercase_base_command}_VERSION": "1.1.8",
            },
            f'/bin/bash -c "scan_{base_command} && {base_command} init -backend=false && {base_command} validate"',
            1,
        ),  # This tests the bring-your-own {uppercase_base_command}_VERSION hook (40-), regardless of the built-in security tools (DISABLE_SECURITY=true)
        # It fails because it ignores the 50- {base_command} due to AUTODETECT=false, and the v_0_14_dir files fail given the
        # version of {uppercase_base_command}_VERSION specified above
    ]
    LOG.debug(
        f"Fail when using a modern version of {base_command} in a repo which expects 0.14.x"
    )
    num_tests_ran += exec_tests(
        tests=tests,
        volumes=hooks_secure_terraform_v_0_14_dir_volumes,
        image=image,
        user=user,
    )

    tests: list[tuple[dict, str, int]] = [  # type: ignore
        (
            {
                "DISABLE_HOOKS": "false",
                "AUTODETECT": "true",
                "DISABLE_SECURITY": "true",
            },
            f'/bin/bash -c "{base_command} init -backend=false && {base_command} validate"',
            0,
        ),  # This tests the {base_command} version switching hook failback due to no network (see exec_tests below)
        # It succeeds because only terraform/hooks/secure_builtin_version/secure.tf is tested, which will validate properly with the version of {base_command}
        # that {uppercase_base_command}_VERSION indicates by default
        (
            {
                "DISABLE_HOOKS": "false",
                "AUTODETECT": "false",
                "DISABLE_SECURITY": "true",
                f"{uppercase_base_command}_VERSION": "1.1.8",
            },
            f'/bin/bash -c "{base_command} init -backend=false && {base_command} validate"',
            0,
        ),  # This tests the bring-your-own {uppercase_base_command}_VERSION hook, regardless of the built-in security tools
        # It succeeds because only terraform/hooks/secure_builtin_version/secure.tf is tested, and it requires a version of {base_command} newer then the
        # provided {uppercase_base_command}_VERSION environment variable specifies, but because there is no network access the change does not take place
    ]
    LOG.debug(
        f"Testing the easy_infra hooks with no network access, against various {base_command} configurations, expecting successes"
    )
    num_tests_ran += exec_tests(
        tests=tests,
        volumes=hooks_secure_terraform_v_builtin_dir_volumes,
        image=image,
        user=user,
        network_mode="none",
    )


def run_ansible(*, image: str, user: str, mount_local_files: bool) -> None:
    """Run the ansible-playbook tests"""
    num_tests_ran = 0
    working_dir = "/iac/"
    volumes: list[dict[Path, dict[str, str]]] = []
    kics_config_dir = TESTS_PATH.joinpath("ansible/tool/kics")
    kics_volumes = {kics_config_dir: {"bind": working_dir, "mode": "rw"}}
    volumes.append(kics_volumes)
    secure_config_dir = TESTS_PATH.joinpath("ansible/general/secure")
    secure_volumes = {secure_config_dir: {"bind": working_dir, "mode": "rw"}}
    volumes.append(secure_volumes)
    secure_volumes_with_log_config = copy.deepcopy(secure_volumes)
    alt_working_dir: str = "/alt_working_dir/"
    alt_bind_secure_volumes = copy.deepcopy(secure_volumes)
    alt_bind_secure_volumes[secure_config_dir]["bind"] = alt_working_dir
    volumes.append(alt_bind_secure_volumes)
    fluent_bit_config_host = TESTS_PATH.joinpath("fluent-bit.outputs.conf")
    fluent_bit_config_container = "/usr/local/etc/fluent-bit/fluent-bit.outputs.conf"
    secure_volumes_with_log_config[fluent_bit_config_host] = {
        "bind": fluent_bit_config_container,
        "mode": "ro",
    }
    volumes.append(secure_volumes_with_log_config)
    if mount_local_files:
        functions_dir = CWD.joinpath("build").joinpath("functions.sh")
        common_dir = CWD.joinpath("build").joinpath("common.sh")
        for volume in volumes:
            volume[functions_dir] = {"bind": "/functions.sh"}
            volume[common_dir] = {"bind": "/usr/local/bin/common.sh"}

    # Test alternative working directories/binds
    # Tests is a list of tuples containing the test environment, command, and expected exit code
    tests: list[tuple[dict, str, int]] = [  # type: ignore
        (
            {},
            "ansible-playbook secure.yml --syntax-check",
            4,
        ),  # Exits 4 because secure.yml is not a valid Play
        ({}, '/bin/bash -c "ansible-playbook secure.yml --syntax-check || false"', 1),
    ]

    LOG.debug("Testing alternative working dirs/binds with the ansible image")
    num_tests_ran += exec_tests(
        tests=tests, volumes=alt_bind_secure_volumes, image=image, user=user
    )

    # Ensure insecure configurations fail due to kics
    # Tests is a list of tuples containing the test environment, command, and
    # expected exit code
    tests: list[tuple[dict, str, int]] = [
        ({}, "ansible-playbook insecure.yml --syntax-check", 50),
        ({}, "scan_ansible", 50),
        ({}, "scan_ansible-playbook", 50),
        ({"DISABLE_SECURITY": "true"}, "scan_ansible-playbook", 0),
        ({}, "scan_ansible --skip-kics", 0),
        (
            {},
            "ansible-playbook --skip-kics insecure.yml --syntax-check",
            4,
        ),  # Exits 4 because insecure.yml is not a valid Play
        (
            {},
            "SKIP_KICS=true ansible-playbook insecure.yml --syntax-check",
            127,
        ),  # Not supported; prepended variables do not work unless the
        #     commands are passed through bash
        (
            {},
            '/usr/bin/env bash -c "ansible-playbook insecure.yml --syntax-check || true"',
            0,
        ),
        (
            {},
            '/usr/bin/env bash -c "LEARNING_MODE=true ansible-playbook insecure.yml --syntax-check"',
            4,
        ),  # Exits 4 because insecure.yml is not a valid Play
        (
            {"LEARNING_MODE": "true"},
            "ansible-playbook insecure.yml --syntax-check",
            4,
        ),  # Exits 4 because insecure.yml is not a valid Play
        (
            {"KICS_INCLUDE_QUERIES": "c3b9f7b0-f5a0-49ec-9cbc-f1e346b7274d"},
            "ansible-playbook insecure.yml --syntax-check",
            4,
        ),  # Exits with 4 because insecure.yml is not a valid Play, and the provided insecure playbook does not apply to the included queries.
        # This tests the "arg_customizations" idea from easy_infra.yml and functions.j2
        (
            {"KICS_INCLUDE_QUERIES": "7dfb316c-a6c2-454d-b8a2-97f147b0c0ff"},
            "ansible-playbook insecure.yml --syntax-check",
            50,
        ),  # This tests the "arg_customizations" idea from easy_infra.yml and functions.j2
        (
            {
                "KICS_EXCLUDE_SEVERITIES": "info,low",
            },
            "ansible-playbook insecure.yml --syntax-check",
            50,
        ),  # Doesn't exclude high or medium.
        # This tests the "arg_customizations" idea from easy_infra.yml and functions.j2
        (
            {
                "KICS_EXCLUDE_SEVERITIES": "high,medium,low",
            },
            "ansible-playbook insecure.yml --syntax-check",
            4,
        ),  # Excludes all the relevant severities, exits 4 because insecure.yml is not a valid Play.
        # This tests the "arg_customizations" idea from easy_infra.yml and functions.j2
        (
            {},
            '/usr/bin/env bash -c "KICS_EXCLUDE_SEVERITIES=info,low,medium,high ansible-playbook insecure.yml --syntax-check"',
            4,
        ),  # Excludes all the severities, exits 4 because insecure.yml is not a valid Play.
        # This tests the "arg_customizations" idea from easy_infra.yml and functions.j2
        # TODO: Test env_customizations
    ]

    num_tests_ran += exec_tests(
        tests=tests, volumes=kics_volumes, image=image, user=user
    )

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
        cmd='/bin/bash -c "ansible-playbook secure.yml --syntax-check"', tty=False
    )
    files = [
        "/tmp/kics_complete",
    ]
    LOG.debug("Testing non-interactive ansible-playbook commands")
    number_of_security_tools = len(constants.CONFIG["packages"]["ansible"]["security"])
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

    # Test the git clone feature
    #
    # Note that we can't just replace the cd with workdir because it will create the dir as root prior to hitting the ENTRYPOINT, and the container
    # user won't have access to write in that directory when it tries to run _clone. This was fixed in buildkit in
    # https://github.com/moby/buildkit/pull/1002 but docker-py doesn't support buildkit yet; see the very popular
    # https://github.com/docker/docker-py/issues/2230 issue from January 2019
    #
    # The exit 230 ensures that, if the dir doesn't exist, it doesn't accidentally match the expected_exit of 1 below
    command = '/bin/bash -c "cd /iac/seisollc/easy_infra/tests/ansible/tool/kics || exit 230 && scan_ansible"'
    LOG.debug("Testing scan_ansible against a repository that was cloned at runtime")
    environment = {}
    environment["VCS_DOMAIN"] = "github.com"
    environment["CLONE_REPOSITORIES"] = "seisollc/easy_infra,seisollc/easy_infra"
    environment["CLONE_PROTOCOL"] = "https"

    # TODO: In the future, migrate this to a general test config

    # Purposefully missing volumes= because we are using clone to do it
    utils.opinionated_docker_run(
        image=image,
        command=command,
        environment=environment,
        expected_exit=50,
    )
    num_tests_ran += 1

    LOG.info(f"{image} passed {num_tests_ran} end to end ansible-playbook tests")


def run_azure(*, image: str, user: str, mount_local_files: bool) -> None:
    """Run the azure tests"""
    num_tests_ran = 0

    if mount_local_files:
        LOG.debug(
            "mount_local_files is not yet implemented for azure environmental tests"
        )

    # Ensure a basic azure help command succeeds
    command = "az help"
    utils.opinionated_docker_run(
        image=image, command=command, user=user, expected_exit=0
    )
    num_tests_ran += 1

    LOG.info(f"{image} passed {num_tests_ran} integration tests as {user}")


def run_aws(*, image: str, user: str, mount_local_files: bool) -> None:
    """Run the aws tests"""
    num_tests_ran = 0

    if mount_local_files:
        LOG.debug(
            "mount_local_files is not yet implemented for azure environmental tests"
        )

    # Ensure a basic aws help command succeeds
    command = "aws help"
    utils.opinionated_docker_run(
        image=image, command=command, user=user, expected_exit=0
    )
    num_tests_ran += 1

    LOG.info(f"{image} passed {num_tests_ran} integration tests as {user}")


def run_security(*, tool: str, environment: str, tag: str) -> None:
    """Run the security tests"""
    sbom_file: Path = Path(f"sbom.{tag}.json")

    if not sbom_file.is_file():
        LOG.debug("Generating an SBOM...")
        utils.sbom(tool=tool, environment=environment)

    # Run a vulnerability scan on the provided SBOM
    try:
        LOG.info(f"Running a vulnerability scan on {sbom_file}...")
        subprocess.run(
            [
                "grype",
                f"sbom:{str(sbom_file)}",
                "--output",
                "json",
                "--file",
                f"vulns.{tag}.json",
            ],
            capture_output=True,
            check=True,
        )
    except subprocess.CalledProcessError as error:
        LOG.error(
            f"stdout: {error.stdout.decode('utf-8')}, stderr: {error.stderr.decode('utf-8')}"
        )
        sys.exit(1)

    image_and_tag: str = f"{constants.IMAGE}:{tag}"
    LOG.info(f"{image_and_tag} passed the security tests")
