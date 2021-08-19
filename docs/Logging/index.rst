*******
Logging
*******

``easy_infra`` uses `fluentbit <https://fluentbit.io/>`_ as its logging agent,
and it is configured by default to write logs in a format very similar to
Elastic Common Schema (ECS) 1.11.

Logs are written within the container to /var/log/easy_infra.log and then
picked up by the agent and shipped off based on the configuration in
``/usr/local/etc/fluent-bit/fluent-bit.conf``

Customizing fluent-bit
----------------------

In order to customize ``fluent-bit``, you can volume mount your preferred
configuration file on top of the ``/usr/local/etc/fluent-bit/fluent-bit.conf``
file at runtime.
