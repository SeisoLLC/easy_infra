*******
Logging
*******

``easy_infra`` uses `fluentbit <https://fluentbit.io/>`_ as its logging agent,
and it is configured by default to write logs in a format very similar to
Elastic Common Schema (ECS) 1.11.

Logs are written within the container to /var/log/easy_infra.log and then
picked up by the agent and shipped off based on the configuration in
``/usr/local/etc/fluent-bit/fluent-bit.conf``, which points to
``fluent-bit.inputs.conf`` and ``fluent-bit.outputs.conf`` in the same
directory to configure inputs and outputs by default.

TLS is enforced in ``easy_infra`` when ``fluent-bit`` is started, via
``docker-entrypoint.sh``.

``fluent-bit`` logs are located in ``/var/log/fluent-bit.log``.

Customizing fluent-bit
----------------------

In order to customize ``fluent-bit``, you can volume mount your preferred
configuration file(s) on top of ``fluent-bit.conf`, ``fluent-bit.inputs.conf``,
``fluent-bit.outputs.conf``, ``parsers.conf``, and/or ``plugins.conf`` from
within the ``/usr/local/etc/fluent-bit/`` folder at runtime.
