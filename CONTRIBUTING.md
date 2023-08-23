# Contributing

## Background

To learn more about the design and background of this project, as well as some of the naming standards and concepts, see [the
documentation](https://easy-infra.readthedocs.io/) under the Technical Details section. You may also want to refer to the other parts of the docs to learn about
the existing features.

## Getting started

To get started with contributing to this project, you first want to ensure that you can build and test the project locally.

First, ensure you have `docker`, `git`, `pipenv`, and `python3` installed locally, and the `docker` daemon is running. Then run `task init` to initialize the
repository.

If you'd like to [run the test suite](#running-the-tests), you will also need `grype` downloaded and in your `PATH`.

If you'd like to [generate an SBOM](#generating-the-sboms), you will also need `syft` downloaded and in your `PATH`.

### Building the images

To build all of the docker images, run:

```bash
task build
```

If you only want to build a specific image, you can pass in a tool and/or an environment. For example:

```bash
TOOL=terraform ENVIRONMENT=none task build
```

To see the list of possible tools, run the following command. If you don't specify a tool, `build` will assume that you want to build "all" of the tools.

```bash
pipenv run python3 -c \
  "from easy_infra import constants; \
  print(list(constants.TOOLS))"
```

To see the possible environments, run the following command. If you don't specify a environment, `build` will assume that you want to build "all" of the
supported environments for the specified tool(s).

```bash
pipenv run python -c \
  "from easy_infra import constants; \
  print(list(constants.ENVIRONMENTS) + ['none'])"
```

If you'd like to see what **would** have been done, and which images would have been built, you can use `--dry-run`, for example:

```bash
pri build --environment=azure --dry-run
```

#### Building in trace mode

If you'd like to build the container locally and allow detailed tracing, run the following:

```bash
TRACE=true task build
```

This will add additional troubleshooting tools to the container, and perform some tracing, putting the details in `/tmp/`.

### Running the tests

If you are attempting to run the tests locally, consider running the following to ensure that the user from inside the container can write to the host:

```bash
find tests -mindepth 1 -type d -exec chmod o+w {} \;
```

You can now run the tests locally:

```bash
task test
```

You can pass in the `--tool`, `--environment`, and `--user` arguments to test a specific subset of functionality. See the build step to see the `tool` and
`environment` possible inputs.

To see the list of supported users, run the following command. If you don't specify a user, `test` will assume that you want to test with all of the supported
users.

```bash
pipenv run python3 -c \
  "from easy_infra import constants; \
  print(constants.USERS)"
```

### Generating the SBOMs

If you'd like to generate an SBOM, run the following:

```bash
task sbom
```

You will now see various `sbom.*.json` files in your current directory, and you can pass in the same `--tool` and `--environment` arguments as `build`ing.

### Running vulnerability scans

If you'd like to run the vulnerability scans, run the following:

```bash
task vulnscan
```

You will now see various `vulns.*.json` files in your current directory, and you can pass in the same `--tool` and `--environment` arguments as outlined in the
build instructions above.
