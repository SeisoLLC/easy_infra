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

    docker run -v $(pwd):/iac seiso/easy_infra:latest-cloudformation aws cloudformation validate-template --template-body file://./example.yaml

You can also use easy_infra to deploy your infrastructure using ``aws cloudformation deploy``::

    docker run -v $(pwd):/iac seiso/easy_infra:latest-cloudformation aws cloudformation deploy --template-file file://./example.yaml --stack-name example


Customizing Checkov
^^^^^^^^^^^^^^^^^^^

+---------------------------------+-----------------------------------------------+----------------------------+
| Environment Variable            | Result                                        | Example                    |
+=================================+===============================================+============================+
| ``CHECKOV_BASELINE``            | Passes the value to ``--baseline``            | ``/iac/.checkov.baseline`` |
+---------------------------------+-----------------------------------------------+----------------------------+
| ``CHECKOV_EXTERNAL_CHECKS_DIR`` | Passes the value to ``--external-checks-dir`` | ``/iac/checkov_rules/``    |
+---------------------------------+-----------------------------------------------+----------------------------+
| ``CHECKOV_SKIP_CHECK``          | Passes the value to ``--skip-check``          | ``CKV_AWS_46``             |
+---------------------------------+-----------------------------------------------+----------------------------+


::

    CHECKOV_BASELINE=/iac/.checkov.baseline
    CHECKOV_EXTERNAL_CHECKS_DIR=/iac/checkov_rules/
    CHECKOV_SKIP_CHECK=CKV_AWS_46
    docker run --env-file <(env | grep ^CHECKOV_) -v $(pwd):/iac easy_infra:latest-cloudformation aws cloudformation validate-template --template-body file://./example.yaml


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

+------------------------+------------------------------+---------------------------------------------------------------------------------------------------+
| Parameter              | Result                       | Example                                                                                           |
+========================+==============================+===================================================================================================+
| ``--disable-security`` | Disable all security tooling | ``aws cloudformation validate-template --disable-security --template-body file://./example.yaml`` |
+------------------------+------------------------------+---------------------------------------------------------------------------------------------------+
| ``--skip-checkov``     | Disable Checkov              | ``aws cloudformation --skip-checkov validate-template --template-body file://./example.yaml``     |
+------------------------+------------------------------+---------------------------------------------------------------------------------------------------+

.. note::
    All command-line arguments in the above table are processed by easy_infra and removed prior to passing parameters to aws cloudformation commands.


Resources
---------

Checkov allow numerous methods for creating custom policies, such as by writing them in Python or using the Checkov-specific DSL in yaml files. These
options are described in more detail `here <https://www.checkov.io/3.Custom%20Policies/Custom%20Policies%20Overview.html>_`
