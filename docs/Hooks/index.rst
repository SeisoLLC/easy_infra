*****
Hooks
*****

``easy_infra`` provides a method for dynamically adding hooks at runtime to any of the components.

When hooks are used in conjunction with ``AUTODETECT``, the registered hooks will be executed in each of the detected folders.

Writing a Hook
--------------

Write a ``.sh`` script and put it in ``/opt/hooks/bin/``, with a comment that follows the below format, where ``terraform`` is the command that you'd
like to hook::

    # register_hook: terraform

.. note::
    Only packages (or their related aliases, where specified) listed in ``easy_infra.yml`` at build time are supported. This means that, if a package has multiple aliases it will need to be registered against each of those aliases.

Example
^^^^^^^

An example minimal hook is as follows::

    #!/usr/bin/env bash
    # register_hook: terraform
    echo "Running hook"

Certain information is also available in the hook, such as the calling directory. You can access it by simply refering the variable ``${dir}``::

    #!/usr/bin/env bash
    # register_hook: terraform
    echo "Running hook from ${dir}"

If you want to add a single hook at runtime, consider::

    docker run -v /path/to/hook/example_hook.sh:/opt/hooks/bin/example_hook.sh seiso/easy_infra:latest-terraform terraform validate

If you want to overwrite all of the built-in hooks with your own folder of hooks, consider::

    docker run -v /path/to/hooks:/opt/hooks/bin/ seiso/easy_infra:latest-terraform terraform validate

Configuring Hooks
-----------------

If you'd like to disable hooks, set the environment variable ``DISABLE_HOOKS`` to ``true``.

+----------------------+-----------+----------------------------------------+
| Environment variable | Default   | Result                                 |
+======================+===========+========================================+
| ``DISABLE_HOOKS``    | ``false`` | Disable all hooks when set to ``true`` |
+----------------------+-----------+----------------------------------------+
