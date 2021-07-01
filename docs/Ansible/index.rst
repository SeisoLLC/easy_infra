Ansible
=======
`Ansible <https://github.com/ansible/ansible>`_ is a "radically simple IT
automation system."

The easy_infra project includes Ansible as a component due to its popularity
and versitility in provisioning and managing systems as Infrastructure as Code
(IaC).


Use Cases
=========

If you use Software Version Control (such as `git`) to manage your Terraform
IaC, consider executing ``terraform validate`` with easy_infra as a pipeline
action on commit or pull request::

    docker run -v $(pwd):/iac seiso/easy_infra:latest-minimal terraform validate

You can also use easy_infra to deploy your infrastructure using ``terraform
plan`` and ``terraform deploy``::

    docker run -v $(pwd):/iac seiso/easy_infra:latest-minimal /bin/bash -c "terraform plan && terraform apply -auto-approve"

Terraform Caching
------------------
If you're working with the same terraform code across multiple runs, you can leverage the cache::

    docker run -v $(pwd):/iac -v $(pwd)/plugin-cache:/root/.terraform.d/plugin-cache easy_infra:latest-minimal /bin/bash -c "terraform init; terraform validate"

Resources
=========
Configuring custom checks can be done by leveragin the robust Rego language, maintained by the, 
Open Policy Agent (OPA) offers useful resources for cloud native infrastructure administrators.
Their example Terraform workflow is available `here  <https://www.openpolicyagent.org/docs/latest/terraform/>`_.

OPA also hosts `The Rego Playground <https://play.openpolicyagent.org/>`_ for testing custom Terrascan rules.

