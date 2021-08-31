*******
Ansible
*******

`Ansible <https://github.com/ansible/ansible>`_ is a "radically simple IT
automation system."

The ``easy_infra`` project includes and secures Ansible as a component due to
its popularity and versitility in provisioning and managing systems as
Infrastructure as Code (IaC).

``easy_infra``'s Ansible security uses tools such as `KICS <https://kics.io/>`_
to semi-transparently assess the provided IaC against the defined security
policy.

.. note::
    The same level of Ansible security is included in all of the ``easy_infra``
    tags, including minimal, aws, az, and latest.


Use Cases
---------

If you use Software Version Control (such as ``git``) to manage your Ansible IaC,
consider executing ``ansible-playbook EXAMPLE.yml --check`` with easy_infra as
a pipeline action on commit or pull request::

    docker run -v $(pwd):/iac seiso/easy_infra:latest-minimal ansible-playbook EXAMPLE.yml --check

Customizing KICS
^^^^^^^^^^^^^^^^

+----------------------+-------------------------------------------+-------------------------------------------------------------------------------+
| Environment variable | Result                                    | Example                                                                       |
+======================+===========================================+===============================================================================+
| ``KICS_QUERIES``     | Passes the value to ``--include-queries`` | ``c3b9f7b0-f5a0-49ec-9cbc-f1e346b7274d,7dfb316c-a6c2-454d-b8a2-97f147b0c0ff`` |
+----------------------+-------------------------------------------+-------------------------------------------------------------------------------+

::

    KICS_QUERIES=c3b9f7b0-f5a0-49ec-9cbc-f1e346b7274d,7dfb316c-a6c2-454d-b8a2-97f147b0c0ff
    docker run --env-file <(env | grep KICS_QUERIES) -v $(pwd):/iac easy_infra:latest-minimal ansible-playbook EXAMPLE.yml --check

Disabling Security
^^^^^^^^^^^^^^^^^^

The injected security tooling can be disabled entirely or individually, using
``easy_infra``-specific command line arguments or environment variables.

+----------------------+-----------+----------------------------------------------------------+
| Environment variable | Default   | Result                                                   |
+======================+===========+==========================================================+
| ``DISABLE_SECURITY`` | ``false`` | Disables all security tooling (Not just Ansible-related) |
+----------------------+-----------+----------------------------------------------------------+
| ``SKIP_KICS``        | ``false`` | Disables KICS                                            |
+----------------------+-----------+----------------------------------------------------------+

+------------------------+------------------------------+-------------------------------------------------------------+
| Parameter              | Result                       | Example                                                     |
+========================+==============================+=============================================================+
| ``--disable-security`` | Disable all security tooling | ``ansible-playbook --disable-security EXAMPLE.yml --check`` |
+------------------------+------------------------------+-------------------------------------------------------------+
| ``--skip-kics``        | Disable KICS                 | ``ansible-playbook --skip-kics EXAMPLE.yml --check``        |
+------------------------+------------------------------+-------------------------------------------------------------+

.. note::
    All command-line arguments in the above table are processed by easy_infra
    and removed prior to passing parameters to Ansible commands.


Resources
---------

Configuring custom checks can be done by leveraging the robust Rego language,
maintained by the, Open Policy Agent (OPA) offers useful resources for cloud
native infrastructure administrators.

OPA also hosts `The Rego Playground <https://play.openpolicyagent.org/>`_ for
testing custom Terrascan rules.
