import os
import sys
import argparse
import logging

from . import iris_utils
import iris

logging.basicConfig(level=logging.INFO)

VENV_BACKUP_GREF = "^Venv.BackUp"

def bind():
    parser = argparse.ArgumentParser()
    parser.add_argument("--namespace", default="")
    args = parser.parse_args()

    iris_gref = iris.gref(VENV_BACKUP_GREF)

    path = ""

    libpython = iris_utils.find_libpython()
    if not libpython:
        logging.error("libpython not found")
        raise RuntimeError("libpython not found")

    iris.system.Process.SetNamespace("%SYS")

    config = iris.cls("Config.config").Open()

    # Set the new libpython path
    iris_gref["PythonRuntimeLibrary"] = config.PythonRuntimeLibrary
        
    config.PythonRuntimeLibrary = libpython

    if "VIRTUAL_ENV" in os.environ:
        # we are not in a virtual environment
        path = os.path.join(os.environ["VIRTUAL_ENV"], "lib", "python" + sys.version[:4], "site-packages")

    iris_gref["PythonPath"] = config.PythonPath

    config.PythonPath = path
    
    config._Save()

    log_config_changes(libpython, path)

def unbind():
    iris.system.Process.SetNamespace("%SYS")
    config = iris.cls("Config.config").Open()

    iris_gref = iris.gref(VENV_BACKUP_GREF)

    if iris_gref["PythonRuntimeLibrary"]:
        config.PythonRuntimeLibrary = iris_gref["PythonRuntimeLibrary"]
    else:
        config.PythonRuntimeLibrary = ""

    if iris_gref["PythonPath"]:
        config.PythonPath = iris_gref["PythonPath"]
    else:
        config.PythonPath = ""

    config._Save()

    del iris_gref["PythonRuntimeLibrary"]
    del iris_gref["PythonPath"]
    del iris_gref[None]

    log_config_changes(config.PythonRuntimeLibrary, config.PythonPath)

def log_config_changes(libpython, path):
    logging.info("PythonRuntimeLibrary path set to %s", libpython)
    logging.info("PythonPath set to %s", path)
    logging.info("To iris instance %s", iris.cls("%SYS.System").GetUniqueInstanceName())
