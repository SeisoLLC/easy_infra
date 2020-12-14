<h1 align="center">Easy Infra[structure as Code]</h1>

easy_infra is a docker container that simplifies and secures Infrastructure as Code deployments.

This is a sample addition

## Quickstart
In order to run your code from within the container, volume mount your files into `/iac` and pass your command, such as `terraform validate`, as such:
```bash
docker run -v $(pwd):/iac seiso/easy_infra terraform validate
```

## Secure by default
This container provides security features by default.  Let's say you are looking to deploy an environment using terraform:
```
docker run -v $(pwd):/iac seiso/easy_infra /bin/bash -c "terraform init && terraform validate && terraform apply"
```
What actually happens is that a security scan of your terraform code will be run prior to executing the first `terraform` command, regardless of what it is.  If an issue is detected, it will exit with a non-zero status, preventing any subsequent execution of `terraform`.

While it's not suggested, if you'd like to disable this behavior you have some options:
1. Set the `SKIP_TFSEC` environment variable to `true`.
    ```bash
    docker run --env SKIP_TFSEC=true -v $(pwd):/iac seiso/easy_infra /bin/bash -c "terraform init && terraform validate && terraform apply"
    ```
1. Pass the `--skip-tfsec` argument to specific `terraform` commands.  Note that this must be the first argument after the `terraform` base command.  It is processed by easy_infra and removed prior to passing parameters to the `terraform` command.
    ```bash
    docker run -v $(pwd):/iac seiso/easy_infra /bin/bash -c "terraform --skip-tfsec init && terraform --skip-tfsec validate && terraform --skip-tfsec apply"
    ```

## Improve Caching
If you're working with the same terraform across multiple runs you can leverage the cache via the following:
```
docker run -v $(pwd):/iac -v $(pwd)/plugin-cache:/root/.terraform.d/plugin-cache easy_infra:latest /bin/bash -c "terraform init; terraform version"
```

## Contributing
1. [Fork the repository](https://github.com/SeisoLLC/easy_infra/fork)
1. Create a feature branch via `git checkout -b feature/description`
1. Make your changes
1. Commit your changes via `git commit -am 'Summarize the changes here'`
1. Create a new pull request ([how-to](https://help.github.com/articles/creating-a-pull-request/))

