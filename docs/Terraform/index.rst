Terraform
=========
HashiCorp's Terraform is a tool for defining your Infrastructure as Code (IaC). The easy_infra project includes Terraform
to support its use, both locally and in CI/CD pipelines. You can use easy_infra to execute Terraform commands, and
as part of the execution, security checks available from `Checkov <https://www.checkov.io/>`_, `tfsec <https://tfsec.dev/>`_, and `Terrascan <https://www.accurics.com/products/terrascan/>`_ are transparently performed to assess your terraform code.

Use Cases
=========
If you use Software Version Control (such as `git`) to manage your Terraform IaC, consider executing ``terraform validate`` with 
easy_infra as a pipeline action on commit or pull request::

    docker run -v $(pwd):/iac seiso/easy_infra:latest-minimal terraform validate

You can also use easy_infra to deploy your infrastructure using ``terraform plan`` and ``terraform deploy``::

    docker run -v $(pwd):/iac seiso/easy_infra:latest-minimal /bin/bash -c "terraform plan && terraform apply -auto-approve"

Terraform Caching
------------------
If you're working with the same terraform code across multiple runs, you can leverage the cache::

    docker run -v $(pwd):/iac -v $(pwd)/plugin-cache:/home/easy_infra/.terraform.d/plugin-cache easy_infra:latest-minimal /bin/bash -c "terraform init; terraform validate"

Resources
=========
Configuring custom checks can be done by leveragin the robust Rego language, maintained by the, 
Open Policy Agent (OPA) offers useful resources for cloud native infrastructure administrators.
Their example Terraform workflow is available `here  <https://www.openpolicyagent.org/docs/latest/terraform/>`_.

OPA also hosts `The Rego Playground <https://play.openpolicyagent.org/>`_ for testing custom Terrascan rules.
