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

## High-Level Design

### Building

When building the `easy_infra` images, the high level design is that files in the `build/` directory are composed together using `tasks.py` to create
multiple final container images for various use cases. Those use cases are primarily based around the use of an IaC "tool" (i.e. `terraform` or
`ansible`), and an associated set of "security tools" (i.e. `checkov` or `kics`) which will run transparently when the IaC tool is used inside of a
container. There are also sometimes optional "environment" (i.e. `aws` or `azure`) images which add environment-specific helpers or tools, based on
the tool that the image focuses on.

There are two general types of files in `build/`; `Dockerfile`s and `Dockerfrag`s.

`Dockerfile`s should be able to be built and tested independently, and are effectively the "install" step of building the `easy_infra` images. It is
possible that an `easy_infra` `Dockerfile` may only contain a `FROM` statement, if we are using a container built and distributed by the upstream
project. `Dockerfile` extensions MUST also be the same as a given `command` as outlined in the `easy_infra.yml` (aliases are not supported), with the
single exception of `Dockerfile.base`.

`Dockerfrag`s cannot be built and tested independently, as they are solely fragments which depend on the related `Dockerfile`. For instance,
`Dockerfrag.terraform` is meant to build on top of `Dockerfile.terraform`. The contents of a `Dockerfrag` often hinge around `COPY`ing files from the
`Dockerfile`. This model allows us to create extremely minimal final images with no bloat or consideration of extraneous packages or dependencies
which are only needed at build time.

In order for a `Dockerfile` and a `Dockerfrag` to be "linked" together, they must share the same extension. For example,`Dockerfrag.abc` should build
on top of `Dockerfile.abc`, and it is both expected that in `Dockerfrag.abc` it copies files using `COPY --from=abc ...`, and that in `Dockerfile.abc`
the `FROM` statement ends with `... as abc`.
