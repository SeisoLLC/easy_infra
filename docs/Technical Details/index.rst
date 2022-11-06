*****************
Technical Details
*****************

easy_infra.yml
==============

``easy_infra`` is a project which makes heavy use of generated code and composable container images. ``easy_infra.yml`` is the centralized
configuration to instruct those generation and composition processes. It describes which version of software to use where, how to generate the very
important ``/functions`` script (more on that in `/functions and functions.j2`_), which is what provides all of the hooking and capabilities.

Here is an ficticious ``easy_infra.yml`` that concisely demonstrates the various features that are possible::

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
    commands:
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
        security: *id002
        validation: *id003
        version: v3.0.0
        version_argument: --version

.. note::
    Not all of these features are used in the default ``easy_infra`` images

YML Anchors and Aliases
-----------------------

Anchors and Aliases are a yml concept, and are fully supported in ``easy_infra.yml`` to support reusable components. See ``&id001`` and ``*id001`` above to see
an example. Learn more `here <https://yaml.org/spec/1.2.2/#3222-anchors-and-aliases>`_ and `here
<https://support.atlassian.com/bitbucket-cloud/docs/yaml-anchors/>`_.

Commands
--------

All of the terms under ``commands`` are the names of packages or tools, and the details of how and when they are installed are described in that
object of the ``easy_infra.yml``. In order to register a runtime hook against a command (Learn more about hooks `here <Hooks/index.html>`_), or define
what security scans occur prior to executing, it must be defined under ``commands``.

Alias
^^^^^

Certain tools have multiple ways to run them, such as by running ``kubectl`` or simply ``k``. These are (often) pointing to the exact same binary, and
if you'd like to support multiple aliases for a tool, provide a list of those aliases under ``alias`` in ``easy_infra.yml``, which will result in
``/functions`` containing an appropriate function hook for each of the aliases.


Allow filter
^^^^^^^^^^^^

The ``allow_filter`` allows you to perform security scans only for a very specific sub-command of a given command. For instance, in the above example,
we have::

    tfenv:
      allow_filter:
      - match: exec
        position: 0

This ensures that, in the generated ``tfenv`` function in ``/functions``, it will check for ``exec`` in the ``0`` position, and only if there's a
match will it continue to perform security scans as described in ``security``.

Allow update
^^^^^^^^^^^^

When projects are added to ``easy_infra`` they are automatically onboarded to our automated maintenance scripts (see ``def update`` under ``tasks.py`` for how
that works). All projectrs that are properly configured will be automatically updated when ``invoke update`` is run, and ``allow_update`` is a boolean field
under that command in ``easy_infra.yml`` which allows the onboarding but exemption of updates to a given project. This is sometimes done when a given project
changes how it performs releases or makes a breaking changes that we have yet to accomodate.

File extensions
^^^^^^^^^^^^^^^

``file_extensions`` were instituted to support the ``AUTODETECT`` function. If a command doesn't have file extensions defined, the project's
autodetect logic is unable to detect where files that relate to the command being run exist.

Security
^^^^^^^^

The backbone of this project is the ``security`` section. All of the terms underneath security define the series of security tools which will be run
every time the related command is run. An alternative ``easy_infra.yml`` would look something like this::

    commands:
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
then it would run both the ``kics`` and ``checkov`` commands as described under ``kics: command: ...`` and ``checkov: command: ...``, with additional
customizations as defined under ``kics: customizations: ...`` and ``checkov: customizations: ...`` when the associated environment variables are set.

As an example, if you ran ``tfenv exec init`` and also had the ``CHECKOV_BASELINE`` environment variable set to ``/iac/.checkov.baseline`` then the actual
checkov command that would be run would be ``checkov -d . --download-external-modules True --skip-download --output json --output-file-path
${CHECKOV_JSON_REPORT_PATH}/checkov.json, --baseline /iac/.checkov.baseline`` (Note the ``--baseline ...`` at the end was dynamically added due to the
enviornment variable).

Validation
^^^^^^^^^^

Sometimes security scanning tools are only equipped to run against IaC which is in a certain state, such as ensuing that the IaC is formatted properly and
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

/functions and functions.j2
===========================

Inside of the container images, ``/functions`` and the related ``BASH_ENV`` environment variable are the functional ways that the security scans, arbitrary
hooks, and logging happens. There are aliases loaded into your environment, which are evaluated prior to searching the ``PATH`` for a file. This means
that when you run ``terraform`` or some other command, it will actually run the function "terraform", which will run the security scans, hooks, and
logging, and only after evaluating the precursor logic will it run ``command terraform`` which runs the ``terraform`` binary.
