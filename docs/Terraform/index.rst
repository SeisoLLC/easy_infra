*********
Terraform
*********

`Terraform <https://github.com/hashicorp/terraform>`_ enables you to safely and
predictably create, change, and improve infrastructure.

The easy_infra project includes and secures Terraform as a component due to its
popularity and versitility in provisioning and updating environments as
Infrastructure as Code (IaC).

``easy_infra``'s Terraform security uses tools such as `KICS
<https://kics.io/>`_, `Checkov <https://www.checkov.io/>`_, `tfsec
<https://tfsec.dev/>`_, and `Terrascan
<https://www.accurics.com/products/terrascan/>`_ to semi-transparently assess
the provided IaC against the defined security policy.

Terraform security is included in all of the ``easy_infra`` tags, including
minimal, aws, az, and latest


Use Cases
---------

If you use Software Version Control (such as ``git``) to manage your Terraform
IaC, consider executing ``terraform validate`` with easy_infra as a pipeline
action on commit or pull request::

    docker run -v $(pwd):/iac seiso/easy_infra:latest-minimal terraform validate

You can also use easy_infra to deploy your infrastructure using ``terraform
plan`` and ``terraform deploy``::

    docker run -v $(pwd):/iac seiso/easy_infra:latest-minimal /bin/bash -c "terraform plan && terraform apply -auto-approve"

Customizing KICS
^^^^^^^^^^^^^^^^

| Environment variable | Result                                    | Example                                                                       |
|----------------------|-------------------------------------------|-------------------------------------------------------------------------------|
| ``KICS_QUERIES``     | Passes the value to ``--include-queries`` | ``4728cd65-a20c-49da-8b31-9c08b423e4db,46883ce1-dc3e-4b17-9195-c6a601624c73`` |

    KICS_QUERIES=4728cd65-a20c-49da-8b31-9c08b423e4db,46883ce1-dc3e-4b17-9195-c6a601624c73
    docker run --env-file <(env | grep KICS_QUERIES) -v $(pwd):/iac easy_infra:latest-minimal terraform validate

Terraform Caching
^^^^^^^^^^^^^^^^^

If you're working with the same terraform code across multiple runs, you can
leverage the cache::

    docker run -v $(pwd):/iac -v $(pwd)/plugin-cache:/home/easy_infra/.terraform.d/plugin-cache easy_infra:latest-minimal /bin/bash -c "terraform init; terraform validate"

Disabling Security
^^^^^^^^^^^^^^^^^^

The injected security tooling can be disabled entirely or individually, using
``easy_infra``-specific command line arguments or environment variables.

| Environment variable | Default   | Result                                                     |
|----------------------|-----------|------------------------------------------------------------|
| ``DISABLE_SECURITY`` | ``false`` | Disables all security tooling (Not just Terraform-related) |
| ``SKIP_CHECKOV``     | ``false`` | Disables Checkov\*                                         |
| ``SKIP_KICS``        | ``false`` | Disables KICS                                              |
| ``SKIP_TERRASCAN``   | ``false`` | Disables Terrascan\*                                       |
| ``SKIP_TFSEC``       | ``false`` | Disables tfsec\*                                           |

| Parameter               | Result                       | Example                                   |
|-------------------------|------------------------------|-------------------------------------------|
| ``--disable-security``  | Disable all security tooling | ``terraform validate --disable-security`` |
| ``--skip-checkov``\**   | Disable Checkov              | ``terraform --skip-checkov validate``     |
| ``--skip-kics``         | Disable KICS                 | ``terraform validate --skip-kics``        |
| ``--skip-terrascan``\** | Disable Terrascan            | ``terraform --skip-terrascan validate``   |
| ``--skip-tfsec``\**     | Disable tfsec                | ``terraform --skip-tfsec validate``       |


\* In the minimal images, only KICS is available

\** This argument is processed by easy_infra and removed prior to passing
parameters to Terraform commands.


Resources
---------

Configuring custom checks can be done by leveragin the robust Rego language,
maintained by the, Open Policy Agent (OPA) offers useful resources for cloud
native infrastructure administrators.  Their example Terraform workflow is
available `here  <https://www.openpolicyagent.org/docs/latest/terraform/>`_.

OPA also hosts `The Rego Playground <https://play.openpolicyagent.org/>`_ for
testing custom Terrascan rules.
