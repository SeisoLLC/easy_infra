# Contributing

## Getting started

Ensure you have `docker`, `git`, `pipenv`, and `python3` installed locally, and the `docker` daemon is running. Then run `pipenv install --deploy
--ignore-pipfile --dev` to install the dependencies onto your local system.

If you'd like to [run the test suite](#running-tests), you will also need `grype` downloaded and in your `PATH`.

If you'd like to [generate an SBOM](#generating-an-sbom), you will also need `syft` downloaded and in your `PATH`.

### Building the image

To build the docker image, run:

```bash
pipenv run invoke build
```

### Running tests

If you are attempting to run the tests locally, consider running the following to ensure that the user from inside the container can write to the
host:

```bash
find tests -mindepth 1 -type d -exec chmod o+w {} \;
```

### Generating an SBOM

If you'd like to generate an SBOM, run the following:

```bash
pipenv run invoke sbom
```

You will now see various `sbom.*.json` files in your current directory.

### Detailed tracing

If you'd like to build the container locally and allow detailed tracing, run the following:

```bash
pipenv run invoke build --trace
```

This will add additional troubleshooting tools to the container, and perform some tracing, putting the details in `/tmp/`.
