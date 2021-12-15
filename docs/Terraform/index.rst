*********
Terraform
*********

`Terraform <https://github.com/hashicorp/terraform>`_ enables you to safely and predictably create, change, and improve infrastructure.

The ``easy_infra`` project includes and secures Terraform as a component due to its popularity and versitility in provisioning and updating
environments as Infrastructure as Code (IaC).

``easy_infra``'s Terraform security uses tools such as `KICS <https://kics.io/>`_, `Checkov <https://www.checkov.io/>`_, `tfsec
<https://tfsec.dev/>`_, and `Terrascan <https://www.accurics.com/products/terrascan/>`_ to semi-transparently assess the provided IaC against the
defined security policy.

Varying levels of Terraform security are included in the ``easy_infra`` tags, including minimal, aws, az, and latest.  For more information, see
`Disabling Security`_ below.

.. note::
    In the minimal, aws, and az images, only the KICS and Checkov security tools are available.  All other security tools will be skipped.


Use Cases
---------

If you use Software Version Control (such as ``git``) to manage your Terraform IaC, consider executing ``terraform validate`` with easy_infra as a
pipeline action on commit or pull request::

    docker run -v $(pwd):/iac seiso/easy_infra:latest-minimal terraform validate

You can also use easy_infra to deploy your infrastructure using ``terraform plan`` and ``terraform deploy``::

    docker run -v $(pwd):/iac seiso/easy_infra:latest-minimal /bin/bash -c "terraform plan && terraform apply -auto-approve"


Customizing Checkov
^^^^^^^^^^^^^^^^^^^

+---------------------------------+-----------------------------------------------+----------------------------+
| Environment Variable            | Result                                        | Example                    |
+=================================+===============================================+============================+
| ``CHECKOV_BASELINE``            | Passes the value to ``--baseline``            | ``/iac/.checkov.baseline`` |
+---------------------------------+-----------------------------------------------+----------------------------+
| ``CHECKOV_EXTERNAL_CHECKS_DIR`` | Passes the value to ``--external-checks-dir`` | ``/iac/checkov_rules/``    |
+---------------------------------+-----------------------------------------------+----------------------------+
| ``CHECKOV_SKIP_CHECK``          | Passes the value to ``--skip-check``          | ``CKV_AWS_20``             |
+---------------------------------+-----------------------------------------------+----------------------------+


::

    CHECKOV_BASELINE=/iac/.checkov.baseline
    CHECKOV_EXTERNAL_CHECKS_DIR=/iac/checkov_rules/
    CHECKOV_SKIP_CHECK=CKV_AWS_20
    docker run --env-file <(env | grep ^CHECKOV_) -v $(pwd):/iac easy_infra:latest-minimal terraform validate


Customizing KICS
^^^^^^^^^^^^^^^^

+-----------------------------+----------------------------------------------+-------------------------------------------------------------------------------+
| Environment variable        | Result                                       | Example                                                                       |
+=============================+==============================================+===============================================================================+
| ``KICS_INCLUDE_QUERIES``    | Passes the value to ``--include-queries``    | ``4728cd65-a20c-49da-8b31-9c08b423e4db,46883ce1-dc3e-4b17-9195-c6a601624c73`` |
+-----------------------------+----------------------------------------------+-------------------------------------------------------------------------------+
| ``KICS_EXCLUDE_SEVERITIES`` | Passes the value to ``--exclude-severities`` | ``info,low``                                                                  |
+-----------------------------+----------------------------------------------+-------------------------------------------------------------------------------+


::

    KICS_INCLUDE_QUERIES=4728cd65-a20c-49da-8b31-9c08b423e4db,46883ce1-dc3e-4b17-9195-c6a601624c73
    KICS_EXCLUDE_SEVERITIES=info,low
    docker run --env-file <(env | grep ^KICS_) -v $(pwd):/iac easy_infra:latest-minimal terraform validate


Customizing tfsec
^^^^^^^^^^^^^^^^^

+--------------------------+----------------------------+----------------------------+
| Environment Variable     | Result                     | Example                    |
+==========================+============================+============================+
| ``TFSEC_DISABLE_CHECKS`` | Passes the value to ``-e`` | ``log-group-customer-key`` |
+--------------------------+----------------------------+----------------------------+


::

    TFSEC_DISABLE_CHECKS=log-group-customer-key
    docker run --env-file <(env | grep ^TFSEC_) -v $(pwd):/iac easy_infra:latest terraform validate


Terraform Caching
^^^^^^^^^^^^^^^^^

If you're working with the same terraform code across multiple runs, you can
leverage the cache::

    docker run -v $(pwd):/iac -v $(pwd)/plugin-cache:/home/easy_infra/.terraform.d/plugin-cache easy_infra:latest-minimal /bin/bash -c "terraform init; terraform validate"


Disabling Security
^^^^^^^^^^^^^^^^^^

The injected security tooling can be disabled entirely or individually, using
``easy_infra``-specific command line arguments or environment variables.

+----------------------+-----------+---------------------------------------------------------------------------------+
| Environment variable | Default   | Result                                                                          |
+======================+===========+=================================================================================+
| ``DISABLE_SECURITY`` | ``false`` | Disables all security tooling (Not just Terraform-related) when set to ``true`` |
+----------------------+-----------+---------------------------------------------------------------------------------+
| ``SKIP_CHECKOV``     | ``false`` | Disables Checkov when set to ``true``                                           |
+----------------------+-----------+---------------------------------------------------------------------------------+
| ``SKIP_KICS``        | ``false`` | Disables KICS when set to ``true``                                              |
+----------------------+-----------+---------------------------------------------------------------------------------+
| ``SKIP_TERRASCAN``   | ``false`` | Disables Terrascan when set to ``true``                                         |
+----------------------+-----------+---------------------------------------------------------------------------------+
| ``SKIP_TFSEC``       | ``false`` | Disables tfsec when set to ``true``                                             |
+----------------------+-----------+---------------------------------------------------------------------------------+

+------------------------+------------------------------+-------------------------------------------+
| Parameter              | Result                       | Example                                   |
+========================+==============================+===========================================+
| ``--disable-security`` | Disable all security tooling | ``terraform validate --disable-security`` |
+------------------------+------------------------------+-------------------------------------------+
| ``--skip-checkov``     | Disable Checkov              | ``terraform --skip-checkov validate``     |
+------------------------+------------------------------+-------------------------------------------+
| ``--skip-kics``        | Disable KICS                 | ``terraform validate --skip-kics``        |
+------------------------+------------------------------+-------------------------------------------+
| ``--skip-terrascan``   | Disable Terrascan            | ``terraform --skip-terrascan validate``   |
+------------------------+------------------------------+-------------------------------------------+
| ``--skip-tfsec``       | Disable tfsec                | ``terraform --skip-tfsec validate``       |
+------------------------+------------------------------+-------------------------------------------+

.. note::
    All command-line arguments in the above table are processed by easy_infra and removed prior to passing parameters to Terraform commands.


Autodetecting files
^^^^^^^^^^^^^^^^^^^

If you'd like to autodetect where your Terraform files exist and run the provided command in each of those detected folders, this is the feature for
you.  This is useful in cases where there is a single repository containing folders which store varying terraform files, and you would like to run a
command (or series of commands) on all of them without needing to maintain a method of looping through them yourself.

+----------------------+-----------+--------------------------------------------------------------------+
| Environment variable | Default   | Result                                                             |
+======================+===========+====================================================================+
| ``AUTODETECT``       | ``false`` | Autodetect folders containing Terraform files when set to ``true`` |
+----------------------+-----------+--------------------------------------------------------------------+

.. note::
    Only .tf files are supported; .tf.json files will not be detected


Resources
---------

Configuring custom checks can be done by leveragin the robust Rego language, maintained by the, Open Policy Agent (OPA) offers useful resources for
cloud native infrastructure administrators.  Their example Terraform workflow is available `here
<https://www.openpolicyagent.org/docs/latest/terraform/>`_.

OPA also hosts `The Rego Playground <https://play.openpolicyagent.org/>`_ for testing custom Terrascan rules.
