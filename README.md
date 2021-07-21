<h1 align="center">Easy Infra[structure as Code]</h1>

easy_infra is a docker container that simplifies and secures Infrastructure as
Code deployments.

## Getting Started

`easy_infra` runs security scans in response to any Ansible or Terraform
command.  It supports three main use cases:

1. **Experimentation** by supporting interactive use and secure
   troubleshooting.
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

What `easy_infra` does in this case is:

1. Perform `terraform` validation, specifically `terraform init && terraform
   validate`
1. Run `terraform` security tools serially, and in alphabetical order
   (`checkov`, `kics`, `terrascan`, and then `tfsec`).
1. Run the provided `terraform` command, assuming the provided configurations
   were confirmed as valid and did not fail any of the security policy
   validation.

### Learning mode

The learning mode suppresses the exit codes of any injected validation or
security tooling, ensuring the provided commands will run.  This can be
configured by setting the `LEARNING_MODE` environment variable to `true`, for
instance:

```bash
docker run -e LEARNING_MODE=true -v $(pwd):/iac seiso/easy_infra terraform apply -auto-approve
```

### Disabling security

The injected security tooling can be disabled entirely or individually, using
`easy_infra`-specific command line arguments or environment variables.

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

\* This argument is processed by easy_infra and removed prior to passing
parameters to the Terraform or Ansible commands.

## Contributing

1. [Fork the repository](https://github.com/SeisoLLC/easy_infra/fork)
1. Create a feature branch via `git checkout -b feature/description`
1. Make your changes
1. Commit your changes via `git commit -am 'Summarize the changes here'`
1. Create a new pull request ([how-to](https://help.github.com/articles/creating-a-pull-request/))
