*******
Cloning
*******

``easy_infra`` allows you to clone git repositories at runtime, based on the configuration options specified below.

Errors encountered during the cloning process are written within the directory that the repos are downloaded in (defaults to ``/iac``), and if any
fatal errors are encountered, a log is written to which can then be centralized for analysis if `Logging <../Logging/index.html>`_ is properly
configured.

Configuration options
^^^^^^^^^^^^^^^^^^^^^

Cloning will only occur when the ``VCS_DOMAIN`` and ``CLONE_REPOSITORIES`` environment variables are set at runtime.

+------------------------+--------------------------------------------+
| Environment Variable   | Example                                    |
+========================+============================================+
| ``VCS_DOMAIN``         | ``github.com``                             |
+------------------------+--------------------------------------------+
| ``CLONE_REPOSITORIES`` | ``seisollc/easy_infra,seisollc/easy_sast`` |
+------------------------+--------------------------------------------+
| ``CLONE_PROTOCOL``     | ``https``                                  |
+------------------------+--------------------------------------------+

.. note::
    Note: Only unauthenticated clones are supported over https. If you do not specify the CLONE_PROTOCOL, or specify it as ssh, you must provide the associated ssh configurations and keys.
