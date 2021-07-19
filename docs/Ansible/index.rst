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


Resources
---------

Configuring custom checks can be done by leveraging the robust Rego language,
maintained by the, Open Policy Agent (OPA) offers useful resources for cloud
native infrastructure administrators.

OPA also hosts `The Rego Playground <https://play.openpolicyagent.org/>`_ for
testing custom Terrascan rules.
