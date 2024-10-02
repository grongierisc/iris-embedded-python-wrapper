import os
import sys
import argparse

from . import iris_utils
import iris


def bind():
    parser = argparse.ArgumentParser()
    parser.add_argument("--namespace", default="")

    args = parser.parse_args()
    path = ""

    libpython = iris_utils.find_libpython()
    if not libpython:
        raise RuntimeError("libpython not found")

    iris.system.Process.SetNamespace("%SYS")
    config = iris.cls("Config.config").Open()

    # Set the new libpython path
    config.PythonRuntimeLibrary = libpython

    if "VIRTUAL_ENV" in os.environ:
        # we are not in a virtual environment
        path = os.path.join(os.environ["VIRTUAL_ENV"], "lib", "python" + sys.version[:4], "site-packages")

    config.PythonPath = path
    
    config._Save()

def unbind():
    iris.system.Process.SetNamespace("%SYS")
    config = iris.cls("Config.config").Open()

    # Set the new libpython path
    config.PythonRuntimeLibrary = ""
    # Set the new PythonPath to VIRTUAL_ENV + "/lib" + "/python+" + sys.version[:4] + "/site-packages
    config.PythonPath = ""

    config._Save()