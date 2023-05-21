*********
Terraform
*********

`Terraform <https://github.com/hashicorp/terraform>`_ enables you to safely and predictably create, change, and improve infrastructure.

The ``easy_infra`` project includes and secures Terraform as a component due to its popularity and versitility in provisioning and updating
environments as Infrastructure as Code (IaC).

``easy_infra`` uses security tools, such as `Checkov <https://www.checkov.io/>`_, to transparently assess the provided IaC against the defined security policy.

.. warning::
    ``easy_infra``'s `terraform` images are incompatable with the terraform ``-chdir`` argument as documented `here
    <https://developer.hashicorp.com/terraform/cli/commands#switching-working-directory-with-chdir>`_.


Use Cases
---------

If you use Software Version Control (such as ``git``) to manage your Terraform IaC, consider executing ``terraform validate`` with easy_infra as a
pipeline action on commit or pull request::

    docker run -v $(pwd):/iac seiso/easy_infra:latest-terraform terraform validate

You can also use easy_infra to deploy your infrastructure using ``terraform plan`` and ``terraform deploy``::

    docker run -v $(pwd):/iac seiso/easy_infra:latest-terraform /bin/bash -c "terraform plan && terraform apply -auto-approve"


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
    docker run --env-file <(env | grep ^CHECKOV_) -v $(pwd):/iac easy_infra:latest-terraform terraform validate


Preinstalled Hooks
^^^^^^^^^^^^^^^^^^

There are some preinstalled hooks in ``/opt/hooks/bin/`` which apply to terraform commands:

* If the ``TERRAFORM_VERSION`` environment variable is customized, easy_infra will attempt to install and switch to that version at runtime. This
  effectively makes it the "new default" in place of the version which was preinstalled in the version of the easy_infra container.
* If ``AUTODETECT`` is set to ``true``, easy_infra will attempt to detect and install the correct version of terraform for each folder that a
  ``terraform`` command runs in using the ``required_version`` block in the code. Since this is module-specific, it will override the default
  terraform version to use (specified by ``TERRAFORM_VERSION``; see the prior bullet).


Terraform Caching
^^^^^^^^^^^^^^^^^

If you're working with the same terraform code across multiple runs, you can leverage the cache::

    docker run -v $(pwd):/iac -v $(pwd)/plugin-cache:/home/easy_infra/.terraform.d/plugin-cache easy_infra:latest-terraform /bin/bash -c "terraform init; terraform validate"


Disabling Security
^^^^^^^^^^^^^^^^^^

The injected security tooling can be disabled entirely or individually, using ``easy_infra``-specific command line arguments or environment variables.

+----------------------+-----------+---------------------------------------------------------------------------------+
| Environment variable | Default   | Result                                                                          |
+======================+===========+=================================================================================+
| ``DISABLE_SECURITY`` | ``false`` | Disables all security tooling (Not just Terraform-related) when set to ``true`` |
+----------------------+-----------+---------------------------------------------------------------------------------+
| ``SKIP_CHECKOV``     | ``false`` | Disables Checkov when set to ``true``                                           |
+----------------------+-----------+---------------------------------------------------------------------------------+

+------------------------+------------------------------+-------------------------------------------+
| Parameter              | Result                       | Example                                   |
+========================+==============================+===========================================+
| ``--disable-security`` | Disable all security tooling | ``terraform validate --disable-security`` |
+------------------------+------------------------------+-------------------------------------------+
| ``--skip-checkov``     | Disable Checkov              | ``terraform --skip-checkov validate``     |
+------------------------+------------------------------+-------------------------------------------+

.. note::
    All command-line arguments in the above table are processed by easy_infra and removed prior to passing parameters to Terraform commands.


Autodetecting files
^^^^^^^^^^^^^^^^^^^

If you'd like to autodetect where your Terraform files exist and run the provided command in each of those detected folders, this is the feature for
you.  This is useful in cases where there is a single repository containing folders which store varying terraform files, and you would like to run a
command (or series of commands) on all of them without needing to maintain a method of looping through them yourself.

+----------------------+-----------+--------------------------------------------------------------------------------------+
| Environment variable | Default   | Result                                                                               |
+======================+===========+======================================================================================+
| ``AUTODETECT``       | ``false`` | Autodetect folders containing Terraform files when set to ``true``                   |
+----------------------+-----------+--------------------------------------------------------------------------------------+
| ``FAIL_FAST``        | ``false`` | Exit as soon as the first failure is encountered, if LEARNING_MODE is also ``false`` |
+----------------------+-----------+--------------------------------------------------------------------------------------+

.. note::
    Only .tf files are supported; .tf.json files will not be detected

.. note::
    When AUTODETECT is enabled, the exit code will be the last non-zero exit code in the series


Resources
---------

Checkov allow numerous methods for creating custom policies, such as by writing them in Python or using the Checkov-specific DSL in yaml files. These options
are described in more detail `here <https://www.checkov.io/3.Custom%20Policies/Custom%20Policies%20Overview.html>`_
