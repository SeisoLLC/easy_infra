# Contributing

1. [Fork the repository](https://github.com/SeisoLLC/easy_infra/fork)
1. Create a feature branch via `git checkout -b feature/description`
1. Make your changes
1. Commit your changes via `git commit -am 'Summarize the changes here'`
1. Create a new pull request ([how-to](https://help.github.com/articles/creating-a-pull-request/))

## Getting started

Ensure you have `docker`, `git`, `pipenv`, and `python3` installed locally, and the `docker` daemon is running. Then run `pipenv install --deploy
--ignore-pipfile --dev` to install the dependencies onto your local system.

If you'd like to [run the test suite](#running-tests), you will also need `grype` downloaded and in your `PATH`.

If you'd like to [generate an SBOM](#generating-an-sbom), you will also need `syft` downloaded and in your `PATH`.

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
