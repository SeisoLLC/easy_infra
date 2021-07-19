<h1 align="center">Easy Infra[structure as Code]</h1>

easy_infra is a docker container that simplifies and secures Infrastructure as
Code deployments.

## Getting Started

`easy_infra` runs its security scans in response to any Ansible or
Terraform command.  It supports three main use cases:

1. **Experimentation** by supporting interactive use and troubleshooting
alongside the security checks.
1. **Continuous Integration** as a part of Pull/Merge Request validation.
1. **Continuous Deployment** as an automated deployment tool.

In order to run your code from within the container, volume mount your files
into `/iac` and pass your command, such as `terraform validate`, as such:

```bash
docker run -v $(pwd):/iac seiso/easy_infra terraform validate
```

## Secure by default

This container provides security features by default.  Deploying an environment
using terraform would likely look something like this:

```bash
docker run -v $(pwd):/iac seiso/easy_infra terraform apply -auto-approve
```

What actually happens is:
1. `terraform` validation occurs, specifically `terraform init && terraform
   validate`
1. Each of the `terraform` security tools are run serially, and in alphabetical
   order (`checkov`, `kics`, `terrascan`, and then `tfsec`).
1. The provided `terraform` command is run, assuming the provided
   configurations were confirmed as valid and did not fail any of the security
   policy validation.

### Learning mode

There is also a learning mode you can enable, which runs all of the security
tooling and prints it output, but suppresses the exit codes to allow the
provided commands to run.  This can be configured by setting the
`LEARNING_MODE` environment variable to `true` like this:

```bash
docker run -e LEARNING_MODE=true -v $(pwd):/iac seiso/easy_infra terraform apply -auto-approve
```

### Disabling security

It's also possible to bypass the security checks, either entirely or
individually, using `easy_infra` specific command line arguments or environment
variables.

| Environment variable | Default | Result                         |
|----------------------|---------|--------------------------------|
| `DISABLE_SECURITY`   | `false` | Disables all security tooling  |
| `SKIP_CHECKOV`       | `false` | Disables Checkov               |
| `SKIP_KICS`          | `false` | Disables KICS                  |
| `SKIP_TERRASCAN`     | `false` | Disables Terrascan             |
| `SKIP_TFSEC`         | `false` | Disables tfsec                 |

| Parameter              | Result                       | Example                                                   |
|------------------------|------------------------------|-----------------------------------------------------------|
| `--disable-security`\* | Disable all security tooling | `ansible-playbook --disable-security example.yml --check` |
| `--skip-checkov`\*     | Disable Checkov              | `terraform --skip-checkov validate`                       |
| `--skip-kics`\*        | Disable KICS                 | `terraform --skip-kics validate`                          |
| `--skip-terrascan`\*   | Disable Terrascan            | `terraform --skip-terrascan validate`                     |
| `--skip-tfsec`\*       | Disable tfsec                | `terraform --skip-tfsec validate`                         |

* This argument is processed by easy_infra and removed prior to passing
parameters to the Terraform or Ansible commands.

## Contributing

1. [Fork the repository](https://github.com/SeisoLLC/easy_infra/fork)
1. Create a feature branch via `git checkout -b feature/description`
1. Make your changes
1. Commit your changes via `git commit -am 'Summarize the changes here'`
1. Create a new pull request ([how-to](https://help.github.com/articles/creating-a-pull-request/))
