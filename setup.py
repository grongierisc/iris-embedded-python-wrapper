from setuptools import setup

# Ship the collision-free startup trigger.  ``iris_ep.pth`` contains an
# import-line that runs ``_iris_ep_sitehook.auto_install()`` at interpreter
# startup, which patches the preloaded built-in ``iris`` module in the IRIS
# embedded-kernel runtime.  Unlike ``sitecustomize`` (a process-wide singleton),
# multiple ``.pth`` import-lines coexist, so this does not collide with other
# packages.  ``.pth`` placement depends on the install layout; ``sitecustomize``
# remains a fallback, and ``iris_ep.install()`` is the explicit API.
setup(
    data_files=[("", ["iris_ep.pth"])],
)
