<h1 align="center">Easy Infra[structure as Code]</h1>

easy_infra is a docker container that simplifies and secures Infrastructure as Code deployments.

## Quickstart
In order to run a command in the container, pass the command at the end of your `docker run` command and pass `docker` any needed files or variables, for instance:
```
docker run --rm -v $(pwd)/key:/keys/key -v $(pwd):/ansible seiso/easy_infra:latest "ansible-playbook -u user -i 192.0.2.230 --private-key /keys/key /ansible/playbook.yml"
```

## Secure by default
This container provides security features by default.  Let's say you are looking to deploy an environment using terraform:
```
docker run --rm -w /tf -v $(pwd):/tf seiso/easy_infra:latest "terraform init && terraform validate && terraform apply"
```
What actually happens is that a security scan of your terraform code will be run prior to executing the `init`, `validate`, and `apply` commands.  If an issue is detected, it will exit with a non-zero status, preventing any subsequent execution of the `terraform` binary.

While it's not suggested, if you'd like to disable this behavior you have some options:
1. Set the `SKIP_TFSEC` environment variable to `true`.
    ```bash
    docker run --rm --env SKIP_TFSEC=true -w /tf -v $(pwd):/tf seiso/easy_infra:latest "terraform init && terraform validate && terraform apply"
    ```
1. Pass the `--skip-tfsec` argument to specific `terraform` commands.  Note that this must be the first argument after the `terraform` base command.  It is processed by easy_infra and removed prior to passing parameters to the `terraform` command.
    ```bash
    docker run --rm -w /tf -v $(pwd):/tf seiso/easy_infra:latest "terraform --skip-tfsec init && terraform --skip-tfsec validate && terraform --skip-tfsec apply"
    ```

## Mermaid-cli
As an interim workaround for `mermaid-cli` (aka `mmdc`), you can specify a puppeteer config which disables sandboxing, for instance:
```bash
mmdc -p /usr/local/etc/puppeteer-config.json -i file.mmd
```

## Contributing
1. [Fork the repository](https://github.com/SeisoLLC/easy_infra/fork)
1. Create a feature branch via `git checkout -b feature/description`
1. Make your changes
1. Commit your changes via `git commit -am 'Summarize the changes here'`
1. Create a new pull request ([how-to](https://help.github.com/articles/creating-a-pull-request/))

