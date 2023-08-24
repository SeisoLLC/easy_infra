*******
Logging
*******

``easy_infra`` uses `fluentbit <https://fluentbit.io/>`_ as its logging agent, and it is configured by default to write logs in a format very similar
to Elastic Common Schema (ECS) 1.11.

Logs are written within the container to ``/var/log/easy_infra.log`` and then picked up by the agent and shipped off based on the configuration in
``/usr/local/etc/fluent-bit/fluent-bit.conf``, which points to ``fluent-bit.inputs.conf`` and ``fluent-bit.outputs.conf`` in the same directory to
configure inputs and outputs by default.

``fluent-bit`` logs are located in ``/var/log/fluent-bit.log``.

Customizing fluent-bit
----------------------

In order to customize ``fluent-bit``, you can volume mount your preferred configuration file(s) on top of ``fluent-bit.conf``,
``fluent-bit.inputs.conf``, ``fluent-bit.outputs.conf``, ``parsers.conf``, and/or ``plugins.conf`` from within the ``/usr/local/etc/fluent-bit/``
folder at runtime.

``fluent-bit`` is configured to read at most 100MB at a time, and up to 10GB of logs for a given run. If you'd like to change this, you can modify or
replace ``Buffer_Chunk_Size`` in ``fluent-bit.inputs.conf``.

Loki example
^^^^^^^^^^^^

If you'd like to run ``terraform validate`` on terraform stored in your current working directory and log the outputs of it to Loki, set the
``LOKI_USER``, ``LOKI_PASSWD``, ``LOKI_TENANT_ID``, and ``LOKI_HOST`` variables appropriately on your host and run the following::

    docker run --env-file <(env | grep ^LOKI_) -v $(pwd)/fluent-bit.loki_example.conf:/usr/local/etc/fluent-bit/fluent-bit.outputs.conf seiso/easy_infra:latest-terraform terraform validate

The contents of ``fluent-bit.loki_example.conf`` here are as follows::

    [OUTPUT]
        Name        loki
        Match       *
        Http_user   ${LOKI_USER}
        Http_passwd ${LOKI_PASSWD}
        Tenant_id   ${LOKI_TENANT_ID}
        Labels      job=easy_infra
        Host        ${LOKI_HOST}
        Port        443
        Tls         On
        Tls.verify  On

For more details on the fluent-bit Loki output plugin, see `this page <https://docs.fluentbit.io/manual/pipeline/outputs/loki>`_.

CloudWatch example
^^^^^^^^^^^^^^^^^^

If you'd like to run ``terraform validate`` on terraform stored in your current working directory and log the outputs of it to CloudWatch, set the
``CW_REGION``, ``CW_LOG_GROUP_NAME``, and ``CW_LOG_STREAM_NAME`` variables appropriately on your host, ensure you are properly logged in using the
``AWS_ACCESS_KEY_ID``, ``AWS_SECRET_ACCESS_KEY``, and any other AWS environment variables (including ``AWS_SESSION_TOKEN`` if you are assuming a role)
environment variables as defined `here<https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-envvars.html>_` and run the following::

    docker run --env-file <(env | grep -E '^CW_|^AWS_') -v $(pwd)/fluent-bit.cw_example.conf:/usr/local/etc/fluent-bit/fluent-bit.outputs.conf seiso/easy_infra:latest terraform validate

The contents of ``fluent-bit.cw_example.conf`` here are as follows::

    [OUTPUT]
        Name               cloudwatch_logs
        Match              *
        Region             ${CW_REGION}
        Log_group_name     ${CW_LOG_GROUP_NAME}
        Log_stream_name    ${CW_LOG_STREAM_NAME}
        Auto_create_group  true

For more details on the fluent-bit Amazon CloudWatch output plugin, including features like cross account role assumption, see `this page
<https://docs.fluentbit.io/manual/pipeline/outputs/cloudwatch>`_.

Volume Mounts
-------------

Mounted directories must be considered "safe" by git, in order for logging to function properly.
When mounting a .git folder into the container, the following variables work together to flag it as a safe directory for git::

    export GIT_CONFIG_COUNT=1
    export GIT_CONFIG_KEY_0="safe.directory"
    GIT_CONFIG_VALUE_0="$(git rev-parse --show-toplevel 2>/dev/null || echo /iac)"
    export GIT_CONFIG_VALUE_0

.. note::

If your mount point and working directory are aligned, you don't need to do anything special; however, if you want to customize 
and volume mount differently than your working directory, ensure you pass an environment variable named GIT_SAFE_DIRECTORY with 
a custom value, for example::

    docker run -it -v /home/user/git_directory:/custom_dir -w /some_other_dir -e GIT_SAFE_DIRECTORY="/custom_dir" seiso/easy_infra:latest-terraform-aws

.. note::
