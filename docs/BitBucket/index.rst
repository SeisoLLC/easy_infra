*********
BitBucket
*********

``easy_infra`` can be used as a BitBucket pipe.

Using the pipe
--------------

An example ``bitbucket-pipeline.yml`` is as follows::

    ---
    image:
      name: atlassian/default-image:4

    test: &test
      step:
        name: Test
        services:
          - docker
        script:
          - pipe: docker://seisollc/easy_infra:2026.02.03-terraform

    pipelines:
      default:
        - <<: *test

Configuring the pipe
--------------------

The pipe accepts the following variables::

+-----------------------+------------------------+------------------------------------------------------------+
| Variable              | Default                | Result                                                     |
+=======================+========================+============================================================+
| ``COMMAND``           | ``terraform validate`` | Sets the command to run in the ``easy_infra`` container    |
+-----------------------+------------------------+------------------------------------------------------------+
| ``LEARNING_MODE``     | ``false``              | Sets ``LEARNING_MODE`` in the ``easy_infra`` container     |
+-----------------------+------------------------+------------------------------------------------------------+
| ``TERRAFORM_VERSION`` | N/A                    | Sets ``TERRAFORM_VERSION`` in the ``easy_infra`` container |
+-----------------------+------------------------+------------------------------------------------------------+

For example::

    ---
    deploy: &deploy
      step:
        name: Deploy
        services:
          - docker
        script:
          - pipe: docker://seisollc/easy_infra:2026.02.03-terraform
            variables:
              COMMAND: /bin/bash -c "terraform plan -out=plan.out && terraform apply -auto-approve plan.out"
              LEARNING_MODE: true
              TERRAFORM_VERSION: 1.6.6

    pipelines:
      default:
        - <<: *deploy
