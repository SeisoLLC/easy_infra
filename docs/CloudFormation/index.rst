**************
CloudFormation
**************

`AWS CloudFormation <https://aws.amazon.com/cloudformation/>`_ enables you to safely and predictably create, change, and improve infrastructure.

The ``easy_infra`` project includes and secures CloudFormation as a component due to its popularity and versitility in provisioning and updating
environments as Infrastructure as Code (IaC).

``easy_infra`` uses security tools, such as `Checkov <https://www.checkov.io/>`_, to transparently assess the provided IaC against the defined security policy.


Use Cases
---------

If you use Software Version Control (such as ``git``) to manage your CloudFormation IaC, consider executing ``aws cloudformation validate-template`` with
easy_infra as a pipeline action on commit or pull request::

    docker run -v .:/iac seiso/easy_infra:latest-cloudformation aws cloudformation validate-template --template-body file://./example.yml

You can also use easy_infra to deploy your infrastructure using ``aws cloudformation deploy``::

    docker run -v .:/iac seiso/easy_infra:latest-cloudformation aws cloudformation deploy --template-file file://./example.yml --stack-name example

.. note::
    In order to run ``aws cloudformation validate-template``, AWS requires that you have an active session with AWS


Customizing Checkov
^^^^^^^^^^^^^^^^^^^

Many of the ``checkov`` command line parameters can be customized or configured at runtime by setting the below environment variables. By setting these
environment variables starting with ``CHECKOV_``, ``easy_infra`` will dynamically add the related arguments to the ``checkov`` security scanning command, and
pass the value of the environment variable to the argument.

For more details regarding how these parameters work, see `the checkov documentation <https://www.checkov.io/2.Basics/CLI%20Command%20Reference.html>`_.

+--------------------------------------------+--------------------------------------+
| Environment Variable                       | CLI Argument                         |
+============================================+======================================+
| ``CHECKOV_BASELINE``                       | ``--baseline``                       |
+--------------------------------------------+--------------------------------------+
| ``CHECKOV_BC_API_KEY``                     | ``--bc-api-key``                     |
+--------------------------------------------+--------------------------------------+
| ``CHECKOV_BLOCK_LIST_SECRET_SCAN``         | ``--block-list-secret-scan``         |
+--------------------------------------------+--------------------------------------+
| ``CHECKOV_CA_CERTIFICATE``                 | ``--ca-certificate``                 |
+--------------------------------------------+--------------------------------------+
| ``CHECKOV_CHECK``                          | ``--check``                          |
+--------------------------------------------+--------------------------------------+
| ``CHECKOV_CREATE_CONFIG``                  | ``--create-config``                  |
+--------------------------------------------+--------------------------------------+
| ``CHECKOV_DOWNLOAD_EXTERNAL_MODULES``      | ``--download-external-modules``      |
+--------------------------------------------+--------------------------------------+
| ``CHECKOV_EVALUATE_VARIABLES``             | ``--evaluate-variables``             |
+--------------------------------------------+--------------------------------------+
| ``CHECKOV_EXTERNAL_CHECKS_DIR``            | ``--external-checks-dir``            |
+--------------------------------------------+--------------------------------------+
| ``CHECKOV_EXTERNAL_CHECKS_GIT``            | ``--external-checks-git``            |
+--------------------------------------------+--------------------------------------+
| ``CHECKOV_EXTERNAL_MODULES_DOWNLOAD_PATH`` | ``--external-modules-download-path`` |
+--------------------------------------------+--------------------------------------+
| ``CHECKOV_HARD_FAIL_ON``                   | ``--hard-fail-on``                   |
+--------------------------------------------+--------------------------------------+
| ``CHECKOV_OPENAI_API_KEY``                 | ``--openai-api-key``                 |
+--------------------------------------------+--------------------------------------+
| ``CHECKOV_POLICY_METADATA_FILTER``         | ``--policy-metadata-filter``         |
+--------------------------------------------+--------------------------------------+
| ``CHECKOV_PRISMA_API_URL``                 | ``--prisma-api-url``                 |
+--------------------------------------------+--------------------------------------+
| ``CHECKOV_REPO_ID``                        | ``--repo-id``                        |
+--------------------------------------------+--------------------------------------+
| ``CHECKOV_REPO_ROOT_FOR_PLAN_ENRICHMENT``  | ``--repo-root-for-plan-enrichment``  |
+--------------------------------------------+--------------------------------------+
| ``CHECKOV_SECRETS_HISTORY_TIMEOUT``        | ``--secrets-history-timeout``        |
+--------------------------------------------+--------------------------------------+
| ``CHECKOV_SECRETS_SCAN_FILE_TYPE``         | ``--secrets-scan-file-type``         |
+--------------------------------------------+--------------------------------------+
| ``CHECKOV_SKIP_CHECK``                     | ``--skip-check``                     |
+--------------------------------------------+--------------------------------------+
| ``CHECKOV_SKIP_CVE_PACKAGE``               | ``--skip-cve-package``               |
+--------------------------------------------+--------------------------------------+
| ``CHECKOV_SOFT_FAIL_ON``                   | ``--soft-fail-on``                   |
+--------------------------------------------+--------------------------------------+
| ``CHECKOV_VAR_FILE``                       | ``--var-file``                       |
+--------------------------------------------+--------------------------------------+

For instance::

    CHECKOV_BASELINE=/iac/.checkov.baseline
    CHECKOV_EXTERNAL_CHECKS_DIR=/iac/checkov_rules/
    CHECKOV_SKIP_CHECK=CKV_AWS_46
    docker run --env-file <(env | grep ^CHECKOV_) -v .:/iac easy_infra:latest-cloudformation aws cloudformation validate-template --template-body file://./example.yml

In addition, you can customize some ``checkov``-specific environment variables at runtime for different effects. By setting these environment variables, you are
customizing the ``checkov`` environment **only** while it is running.

+-----------------------+---------------------+
| Environment Variable  | Checkov Environment |
+=======================+=====================+
| ``CHECKOV_LOG_LEVEL`` | ``LOG_LEVEL``       |
+-----------------------+---------------------+

For instance, the following command will run with ``checkov`` in debug mode (which is separate from running ``easy_infra`` in debug mode)::

    CHECKOV_LOG_LEVEL=DEBUG
    docker run --env CHECKOV_LOG_LEVEL -v .:/iac easy_infra:latest-cloudformation aws cloudformation validate-template --template-body file:///./example.yml


Disabling Security
^^^^^^^^^^^^^^^^^^

The injected security tooling can be disabled entirely or individually, using ``easy_infra``-specific command line arguments or environment variables.

+----------------------+-----------+--------------------------------------------------------------------------------------+
| Environment variable | Default   | Result                                                                               |
+======================+===========+======================================================================================+
| ``DISABLE_SECURITY`` | ``false`` | Disables all security tooling (Not just CloudFormation-related) when set to ``true`` |
+----------------------+-----------+--------------------------------------------------------------------------------------+
| ``SKIP_CHECKOV``     | ``false`` | Disables Checkov when set to ``true``                                                |
+----------------------+-----------+--------------------------------------------------------------------------------------+

+------------------------+------------------------------+--------------------------------------------------------------------------------------------------+
| Parameter              | Result                       | Example                                                                                          |
+========================+==============================+==================================================================================================+
| ``--disable-security`` | Disable all security tooling | ``aws cloudformation validate-template --disable-security --template-body file://./example.yml`` |
+------------------------+------------------------------+--------------------------------------------------------------------------------------------------+
| ``--skip-checkov``     | Disable Checkov              | ``aws cloudformation --skip-checkov validate-template --template-body file://./example.yml``     |
+------------------------+------------------------------+--------------------------------------------------------------------------------------------------+

.. note::
    All command-line arguments in the above table are processed by easy_infra and removed prior to passing parameters to aws cloudformation commands.


Resources
---------

Checkov allow numerous methods for creating custom policies, such as by writing them in Python or using the Checkov-specific DSL in yml files. These
options are described in more detail `here <https://www.checkov.io/3.Custom%20Policies/Custom%20Policies%20Overview.html>`_
