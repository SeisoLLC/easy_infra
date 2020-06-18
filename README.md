<h1 align="center">Easy Infra[structure as Code]</h1>

easy_infra is a docker container that simplifies and secures Infrastructure as Code deployments.

## Quickstart
In order to run a command in the container, pass the command at the end of your `docker run` command and pass `docker` any needed files or variables, for instance:
```
docker run --rm -v $(pwd)/key:/root/keys/key -v $(pwd):/root/ansible seiso/easy_infra:latest "ansible-playbook -u user -i 192.0.2.230 --private-key /root/keys/key /root/ansible/playbook.yml"
```

## Secure by default
This container provides security features by default.  Let's say you are looking to deploy an environment using terraform:
```
docker run --rm -w /root/terraform -v $(pwd)/terraform:/root/terraform seiso/easy_infra:latest "terraform init && terraform apply"
```
What actually happens is that a security scan of your terraform code will be run prior to executing the `init` and `apply` commands.  If an issue is detected, it will exit with a non-zero status, preventing any subsequent execution of the `terraform` binary.

While it's not suggested, if you'd like to disable this behavior you have some options:
1. Set the `SKIP_TFSEC` environment variable to `true`.  This is the preferred option because it is (1) global, and (2) allows you to run native `terraform` commands.
    ```bash
    docker run --rm --env SKIP_TFSEC=true -w /root/tf_dir -v $(pwd)/tf_dir:/root/tf_dir seiso/easy_infra:latest "terraform init && terraform apply"
    ```
1. Pass the `--skip-tfsec` argument to any `terraform` commands.  Note that this is specific to easy_infra, and must be the first argument after the `terraform` base command.  It is processed and removed from the `terraform` command before it is run.
    ```bash
    docker run --rm -w /root/tf_dir -v $(pwd)/tf_dir:/root/tf_dir seiso/easy_infra:latest "terraform --skip-tfsec init && terraform --skip-tfsec apply"
    ```

## Contributing
1. [Fork the repository](https://github.com/SeisoLLC/easy_infra/fork)
1. Create a feature branch via `git checkout -b feature/description`
1. Make your changes
1. Commit your changes via `git commit -am 'Summarize the changes here'`
1. Create a new pull request ([how-to](https://help.github.com/articles/creating-a-pull-request/))

