*******
Logging
*******

``easy_infra`` uses `fluentbit <https://fluentbit.io/>`_ as its logging agent,
and it is configured by default to write logs in a format very similar to
Elastic Common Schema (ECS) 1.11.

Logs are written within the container to ``/var/log/easy_infra.log`` and then
picked up by the agent and shipped off based on the configuration in
``/usr/local/etc/fluent-bit/fluent-bit.conf``, which points to
``fluent-bit.inputs.conf`` and ``fluent-bit.outputs.conf`` in the same
directory to configure inputs and outputs by default.

``fluent-bit`` logs are located in ``/var/log/fluent-bit.log``.

Customizing fluent-bit
----------------------

In order to customize ``fluent-bit``, you can volume mount your preferred
configuration file(s) on top of ``fluent-bit.conf``, ``fluent-bit.inputs.conf``,
``fluent-bit.outputs.conf``, ``parsers.conf``, and/or ``plugins.conf`` from
within the ``/usr/local/etc/fluent-bit/`` folder at runtime.

For example, if you'd like to run ``terraform validate`` on terraform stored in
your current working directory and log the outputs of it to Loki, set the
``LOKI_USER``, ``LOKI_PASSWD``, ``LOKI_TENANT_ID``, and ``LOKI_HOST`` variables
appropriately on your host and run the following::

    docker run --env-file <(env | grep ^LOKI_) -v $(pwd)/fluent-bit.example.conf:/usr/local/etc/fluent-bit/fluent-bit.outputs.conf seiso/easy_infra:latest-minimal terraform validate

The contents of fluent-bit.example.com here are as follows::

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
