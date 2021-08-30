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

To learn more, check out [our
documentation](https://easy_infra.readthedocs.io/) and
[CONTRIBUTING.md](./CONTRIBUTING.md).

## Secure by default

This container provides security features by default.  Deploying an environment
using terraform would likely look something like this:

```bash
docker run -v $(pwd):/iac seiso/easy_infra terraform apply -auto-approve
```

What `easy_infra` does in this case is:

1. Perform `terraform` validation, specifically `terraform init && terraform
   validate`
1. Run `terraform` security tools\* serially, and in alphabetical order
   (`checkov`, `kics`, `terrascan`, and then `tfsec`).
1. Run the provided `terraform` command, assuming the provided configurations
   were confirmed as valid and did not fail any of the security policy
   validation.

\* In the minimal images, only KICS is available

### Learning mode

The learning mode suppresses the exit codes of any injected validation or
security tooling, ensuring the provided commands will run.  This can be
configured by setting the `LEARNING_MODE` environment variable to `true`, for
instance:

```bash
docker run -e LEARNING_MODE=true -v $(pwd):/iac seiso/easy_infra terraform apply -auto-approve
```

### Debugging

If you'd like to enable debug logs at runtime, pass an environment variable of
`LOG_LEVEL` with a value of `DEBUG`, such as:

```bash
docker run -e LOG_LEVEL=DEBUG -v $(pwd):/iac seiso/easy_infra terraform validate
```
