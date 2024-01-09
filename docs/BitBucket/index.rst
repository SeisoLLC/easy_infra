*********
BitBucket
*********

``easy_infra`` provides a BitBucket pipe for ``terraform``.

Using the pipe
--------------

An example ``bitbucket-pipeline.yml`` is as follows::

    #!/usr/bin/env bash
    ---
    image:
      name: atlassian/default-image:4

    test: &test
      step:
        name: Test
        services:
          - docker
        script:
          - pipe: seisollc/easy_infra:latest

    pipelines:
      default:
        - <<: *test

Configuring the pipe
--------------------

The pipe takes the following variables::

+-----------------------+------------------------+------------------------------------------------------------+
| Variable              | Default                | Result                                                     |
+=======================+========================+============================================================+
| ``COMMAND``           | ``terraform validate`` | Sets the command to run in the ``easy_infra`` container    |
+-----------------------+------------------------+------------------------------------------------------------+
| ``LEARNING_MODE``     | ``false``              | Sets ``LEARNING_MODE`` in the ``easy_infra`` container     |
+-----------------------+------------------------+------------------------------------------------------------+
| ``TERRAFORM_VERSION`` | N/A                    | Sets ``TERRAFORM_VERSION`` in the ``easy_infra`` container |
+-----------------------+------------------------+------------------------------------------------------------+
