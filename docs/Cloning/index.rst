*******
Cloning
*******

``easy_infra`` allows you to clone git repositories at runtime, based on the configuration options specified below.

Cloning logs are written to ``/var/log/clone.log``, and if there are any errors they are written to ``/var/log/clone.err.log``.
If fatal errors are encountered, they are centrally logged for analysis if `Logging <../Logging/index.html>`_ is properly
configured.

Configuration options
^^^^^^^^^^^^^^^^^^^^^

Cloning will only occur when the ``VCS_DOMAIN`` and ``CLONE_REPOSITORIES`` environment variables are set at runtime. The other environment variables
are optional.

+------------------------+--------------------------------------------+
| Environment Variable   | Example                                    |
+========================+============================================+
| ``VCS_DOMAIN``         | ``github.com``                             |
+------------------------+--------------------------------------------+
| ``CLONE_REPOSITORIES`` | ``seisollc/easy_infra,seisollc/easy_sast`` |
+------------------------+--------------------------------------------+
| ``CLONE_PROTOCOL``     | ``https``                                  |
+------------------------+--------------------------------------------+
| ``CLONE_DIRECTORY``    | ``/iac``                                   |
+------------------------+--------------------------------------------+

.. note::
    Note: Only unauthenticated clones are supported over https. If you do not specify the CLONE_PROTOCOL, or specify it as ssh, you must provide the associated ssh configurations and keys.
