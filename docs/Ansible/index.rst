*******
Ansible
*******

`Ansible <https://github.com/ansible/ansible>`_ is a "radically simple IT
automation system."

The easy_infra project includes and secures Ansible as a component due to its
popularity and versitility in provisioning and managing systems as
Infrastructure as Code (IaC).

``easy_infra``'s Ansible security uses tools such as `KICS <https://kics.io/>`_
to semi-transparently assess the provided IaC against the defined security
policy.

Ansible security is included in all of the ``easy_infra`` tags, including
minimal, aws, az, and latest


Use Cases
---------

If you use Software Version Control (such as ``git``) to manage your Ansible IaC,
consider executing ``ansible-playbook EXAMPLE.yml --check`` with easy_infra as
a pipeline action on commit or pull request::

    docker run -v $(pwd):/iac seiso/easy_infra:latest-minimal ansible-playbook EXAMPLE.yml --check

Customizing KICS
^^^^^^^^^^^^^^^^

| Environment variable | Result                                    | Example                                                                       |
|----------------------|-------------------------------------------|-------------------------------------------------------------------------------|
| ``KICS_QUERIES``     | Passes the value to ``--include-queries`` | ``4728cd65-a20c-49da-8b31-9c08b423e4db,46883ce1-dc3e-4b17-9195-c6a601624c73`` |

    KICS_QUERIES=4728cd65-a20c-49da-8b31-9c08b423e4db,46883ce1-dc3e-4b17-9195-c6a601624c73
    docker run --env-file <(env | grep KICS_QUERIES) -v $(pwd):/iac easy_infra:latest-minimal terraform validate

Disabling Security
^^^^^^^^^^^^^^^^^^

The injected security tooling can be disabled entirely or individually, using
``easy_infra``-specific command line arguments or environment variables.

| Environment variable | Default   | Result                         |
|----------------------|-----------|--------------------------------|
| ``DISABLE_SECURITY`` | ``false`` | Disables all security tooling  |
| ``SKIP_KICS``        | ``false`` | Disables KICS                  |

| Parameter                | Result                       | Example                                                     |
|--------------------------|------------------------------|-------------------------------------------------------------|
| ``--disable-security``\* | Disable all security tooling | ``ansible-playbook --disable-security example.yml --check`` |
| ``--skip-kics``\*        | Disable KICS                 | ``ansible-playbook --skip-kics example.yml --check``        |

\* This argument is processed by easy_infra and removed prior to passing
parameters to the Terraform or Ansible commands.


Resources
---------

Configuring custom checks can be done by leveraging the robust Rego language,
maintained by the, Open Policy Agent (OPA) offers useful resources for cloud
native infrastructure administrators.

OPA also hosts `The Rego Playground <https://play.openpolicyagent.org/>`_ for
testing custom Terrascan rules.
