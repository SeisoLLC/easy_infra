*****************
Technical Details
*****************

easy_infra.yml
==============

``easy_infra`` is a project which makes heavy use of generated code and composable container images. ``easy_infra.yml`` is the centralized
configuration to instruct those generation and composition processes. It describes which version of software to use, where, how to generate the very
important ``/functions`` script (more on that in `/functions and functions.j2`_), which is what provides all of the hooking and capabilities.

Here is a ficticious ``easy_infra.yml`` that concisely demonstrates the various features that are possible::

    _anchors:
      file_extensions: &id001
      - tf
      security: &id002
        checkov:
          command: checkov -d . --download-external-modules True --skip-download --output
            json --output-file-path ${CHECKOV_JSON_REPORT_PATH}/checkov.json,
          customizations:
            CHECKOV_BASELINE: --baseline
          description: directory scan
      validation: &id003
      - command: terraform init -backend=false
        description: initialization
      - command: terraform validate
        description: validation
    packages:
      fluent-bit:
        helper: ["all"]
        version: v2.0.5
        version_argument: --version
      checkov:
        allow_update: False
        version: 2.2.8
        version_argument: --version
      tfenv:
        aliases:
        - tfe
        allow_filter:
        - match: exec
          position: 0
        file_extensions: *id001
        helper: ["terraform"]
        security: *id002
        validation: *id003
        version: v3.0.0
        version_argument: --version

.. note::
    Not all of these features are always in use in ``easy_infra.yml``

YAML Anchors and Aliases
------------------------

Anchors and Aliases are a yaml concept, and are fully supported in ``easy_infra.yml`` to support reusable components. See ``&id001`` and ``*id001``
above to see an example. Learn more `here <https://yaml.org/spec/1.2.2/#3222-anchors-and-aliases>`_ and `here
<https://support.atlassian.com/bitbucket-cloud/docs/yaml-anchors/>`_.

Packages
--------

All of the terms under ``packages`` are the names of packages, and the details of how and when they are installed are described in that object of the
``easy_infra.yml``. In order to register a runtime hook against a package (Learn more about hooks `here <../Hooks/index.html>`_), or define what
security scans occur prior to executing, it must be defined under ``packages``.

Alias
^^^^^

Certain tools have multiple ways to run them, such as by running ``kubectl`` or simply ``k``. These aliases often point to the exact same binary, and
if you'd like to support multiple aliases for a tool, provide a list of those aliases under ``aliases`` in ``easy_infra.yml``, which will result in
``/functions`` containing an appropriate function hook for each of the aliases.


Allow filter
^^^^^^^^^^^^

The ``allow_filter`` allows you to perform security scans only for a very specific sub-command of a given package or alias. For instance, in the above
example, we have::

    tfenv:
      allow_filter:
      - match: exec
        position: 0

This ensures that, in the generated ``tfenv`` function in ``/functions``, it will check for ``exec`` in the ``0``th position (0-indexed, starting
after the command, and after any easy_infra specific arguments have been removed (i.e. ``--skip-checkov``)), and only if there's a match will it
continue to perform security scans as described in the ``security`` object under the respective ``package`` (i.e. ``tfenv``).

Allow update
^^^^^^^^^^^^

When projects are added to ``easy_infra`` they are automatically onboarded to our automated maintenance scripts (see ``def update`` in ``tasks.py``
for how that works). All projects that are properly configured will be automatically updated when ``invoke update`` is run, and ``allow_update`` is a
boolean field under that package in ``easy_infra.yml`` which allows the onboarding of a package, while exempting it from automatic updates. This is
typically temporary, and only done when a given project changes how it performs releases or makes a breaking changes that we have yet to accomodate.

File extensions
^^^^^^^^^^^^^^^

``file_extensions`` exist to support the ``AUTODETECT`` function. If a ``package`` doesn't have file extensions defined, the project's autodetect
logic is unable to detect where files that relate to the command being run exist.

Security
^^^^^^^^

The backbone of this project is the ``security`` section. All of the terms underneath security define the series of security tools which will be run
every time the related command is run. An alternative ``easy_infra.yml`` would look something like this::

    packages:
      checkov:
        version: 2.2.8
        version_argument: --version
      kics:
        version: v1.5.1
        version_argument: version
      tfenv:
        aliases:
        - tfe
        allow_filter:
        - match: exec
          position: 0
        file_extensions:
        - .tf
        security:
          checkov:
            command: checkov -d . --download-external-modules True --skip-download --output
              json --output-file-path ${CHECKOV_JSON_REPORT_PATH}/checkov.json,
            customizations:
              CHECKOV_BASELINE: --baseline
              CHECKOV_EXTERNAL_CHECKS_DIR: --external-checks-dir
              CHECKOV_SKIP_CHECK: --skip-check
            description: directory scan
          kics:
            command: kics scan --type Terraform --no-progress --queries-path ${KICS_INCLUDE_QUERIES_PATH}
              --libraries-path ${KICS_LIBRARY_PATH} --report-formats json --output-path
              ${KICS_JSON_REPORT_PATH} --output-name kics --path .
            customizations:
              KICS_EXCLUDE_SEVERITIES: --exclude-severities
              KICS_INCLUDE_QUERIES: --include-queries
            description: directory scan
        version: v3.0.0
        version_argument: --version

After building ``easy_infra`` with this configuration, you should be able to expect that when you run ``tfenv exec init`` inside of an ``easy_infra`` container,
then it would run both the ``kics`` and ``checkov`` security tools as described under ``kics: command: ...`` and ``checkov: command: ...``, with additional
customizations as defined under ``kics: customizations: ...`` and ``checkov: customizations: ...`` when the associated environment variables are set.

As an example, if you ran ``tfenv exec init`` and also had the ``CHECKOV_BASELINE`` environment variable set to ``/iac/.checkov.baseline`` then the
actual checkov command that would be run would be::

    checkov -d . --download-external-modules True --skip-download --output json --output-file-path ${CHECKOV_JSON_REPORT_PATH}/checkov.json,
    --baseline /iac/.checkov.baseline

.. note::
    The ``--baseline ...`` at the end was dynamically added due to the enviornment variable.

Validation
^^^^^^^^^^

Sometimes security scanning tools are only equipped to run against IaC which is in a certain state, such as ensuring that the IaC is formatted properly and
valid. ``validation`` is where you can specify what those are, and you can specify a list of commands to run in the specified order, prior to running the
security scanning tools.

Version
^^^^^^^

``version`` is where you can specify which versions of tool you want to include when you're buliding an ``easy_infra`` image. This is what is maintained by this
project's automated maintenance scripts, and it is parsed into build arguments which are passed into the container image building process.

Version Argument
^^^^^^^^^^^^^^^^

``version_argument`` is a way for us to describe how a command requests its version inside of ``easy_infra``. This is useful to know because we avoid running
security scans (and validation, if any is specified) when the version of a tool is being queried inside of an ``easy_infra`` container.

build/
======

``Dockerfile``s must all be able to be built independently, as long as their pre-requisites are met. Typically this means you pass in the appropriate
``*_VERSION`` build arguments, and you pass in an ``EASY_INFRA_TAG`` build argument that maps to a seiso/easy_infra_base tag locally. For example,
a command like the following should work when run from the ``build`` directory if seiso/easy_infra_base:2022.11.06-terraform-943a052 is available
locally::

    docker build -t ansible-test --build-arg ANSIBLE_VERSION=2.9.6+dfsg-1 --build-arg EASY_INFRA_TAG=2022.11.06-terraform-943a052 . -f
    Dockerfile.ansible

``Dockerfrag``s cannot be built individually and are only fragments of an image specification. They are meant to be layered on top of their respective
``Dockerfile``.

/functions and functions.j2
^^^^^^^^^^^^^^^^^^^^^^^^^^^

``functions.j2`` is a Jinja2 template, which is rendered into a ``functions`` script, and then copied into each ``easy_infra`` image at build time.
This all works based on the combination of this ``/functions`` file existing inside of the container, commands being run from within a shell (whether
or not you specify ``bash -c`` or not when running a container), and the ``BASH_ENV`` environment variable pointing to ``/functions``. The way that we
ensure that all commands are run inside a shell is by using ``"$@"`` in the ``easy_infra`` image ``entrypoint`` of ``docker-entrypoint.sh``.

Because ``BASH_ENV`` will ensure that ``/functions`` is loaded into the shell at initialization, and ``/functions`` contains functions which match the
name of tools which we are protecting, we can use those functions to perform security scans, arbitrary hooks, and logging prior to executing the
original command.

Ultimately, this means that when you run ``terraform`` (or some other properly defined package in `easy_infra.yml`_) inside of ``easy_infra``, it will
actually run the function "terraform", which will run the security scans, hooks, and logging, and only after evaluating the precursor logic will it
run ``command terraform`` which runs the ``terraform`` binary from the ``PATH``.

Internal naming
===============

- Tool: An executable file in the easy_infra user's ``PATH`` which perform IaC actions and has an associated security tool, as described in the
  easy_infra.yml used when building the image.
- Security tool: An executable file in the easy_infra user's ``PATH`` which is configured to perform a security scan for an associated "tool" (see
  above), as configured in the ``easy_infra.yml`` file used to build the image.
- Package: The name of a package that can be installed to perform a necessary function. It could be a tool, a security tool, or a generic helper such
  as ``fluent-bit`` or ``envconsul``.
- Command: A runtime command, following the use of the term by bash (see the "Command Execution" of this documentation). This could be an alias, a
  package, or some other executable on the user's ``PATH``.
- Alias: An executable file in the easy_infra user's ``PATH`` which executes the installed by a package. While ``aws-cli`` would be a package, ``aws``
  would be the associated alias.
- Environment: A supported destination that a tool (see above) may deploy into, such as a cloud provider. An environment constitutes a bundle of
  packages.


High-Level Design of the image build process
============================================

When building the ``easy_infra`` images, the high level design is that files in the ``build/`` directory are composed together using ``tasks.py`` to
create multiple final container images for various use cases. Those use cases are primarily based around the use of an IaC "tool" (i.e. ``terraform``
or ``ansible``), and an associated set of "security tools" (i.e. ``checkov`` or ``kics``) which will run transparently when the IaC tool is used
inside of a container. There are also sometimes optional "environment" (i.e. ``aws`` or ``azure``) images which add environment-specific helpers or
tools, based on the tool that the image focuses on.

There are two general types of files in ``build/``; ``Dockerfile``s and ``Dockerfrag``s.

``Dockerfile``s should be able to be built and tested independently, and are effectively the "install" step of building the ``easy_infra`` images. It
is possible that an ``easy_infra`` ``Dockerfile`` may only contain a ``FROM`` statement, if we are using a container built and distributed by the
upstream project. ``Dockerfile`` suffixes MUST also be the same as a given ``package`` as outlined in the ``easy_infra.yml`` (aliases are not
supported), with the single exception of ``Dockerfile.base`` (for example, the ``terraform`` package's ``Dockerfile`` must be
``Dockerfile.terraform``).

``Dockerfrag``s should not be built and tested independently, as they are solely fragments which depend on the related ``Dockerfile``. For instance,
``Dockerfrag.terraform`` is meant to build on top of ``Dockerfile.terraform``. The contents of a ``Dockerfrag`` often hinge around ``COPY``ing files
from the ``Dockerfile``. This model allows us to create extremely minimal final images with limited bloat and consideration of extraneous packages or
dependencies which are only needed at build time.

In order for a ``Dockerfile`` and a ``Dockerfrag`` to be "linked" together, they must share the same suffix. For example,``Dockerfrag.abc`` should
build on top of ``Dockerfile.abc``, and it is both expected that in ``Dockerfrag.abc`` it copies files using ``COPY --from=abc ...``, and that in
``Dockerfile.abc`` the ``FROM`` statement ends with ``... as abc``.

Adding to the project
=====================

Below is a brief checklist to follow when adding a new tool or environment to ``easy_infra``.

Adding a tool
^^^^^^^^^^^^^

- Add the package to ``easy-infra.yml`` under ``packages`` and include a valid ``security``, ``file_extensions``, ``version``, and
  ``version_argument`` section. Consider other optional configurations as they apply (see [the docs]() for more details).

Adding an environment
^^^^^^^^^^^^^^^^^^^^^

-

.. note::
    If you need any special configuration at build time specific to the combination of a tool and an environment, you can create a
    ``Dockerfile.tool-environment`` and ``Dockerfrag.tool-environment``. These are entirely optional.
