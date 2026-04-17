import os
import sys
import importlib
import logging

logging.basicConfig(level=logging.INFO)

from .iris_ipm import ipm
from ._dbapi import make_dbapi
from iris_utils import NativeClassProxy, runtime as _runtime_manager, update_dynalib_path

# check for install dir in environment
# environment to check is IRISINSTALLDIR
# if not found, raise exception and exit
# ISC_PACKAGE_INSTALLDIR - defined by default in Docker images
installdir = os.environ.get('IRISINSTALLDIR') or os.environ.get('ISC_PACKAGE_INSTALLDIR')
__sysversion_info = sys.version_info
__syspath = sys.path
__osname = os.name

_runtime_manager.configure(install_dir=installdir)

if installdir is None:
    logging.warning("IRISINSTALLDIR or ISC_PACKAGE_INSTALLDIR environment variable must be set")
    logging.warning("Embedded Python not available")
else:
    # join the install dir with the bin directory
    __syspath.append(os.path.join(installdir, 'bin'))
    # also append lib/python
    __syspath.append(os.path.join(installdir, 'lib', 'python'))

    # update the dynalib path
    update_dynalib_path(os.path.join(installdir, 'bin'))

# save working directory
__ospath = os.getcwd()

if bool(getattr(sys, "_embedded", 0)):
    # python(libpython.so) inside iris
    from irisep import *
    from irisep import __getattr__
else:

    __irispythonint = None

    if __osname=='nt':
        if __sysversion_info.minor==9:
            __irispythonint = 'pythonint39'
        elif __sysversion_info.minor==10:
            __irispythonint = 'pythonint310'
        elif __sysversion_info.minor==11:
            __irispythonint = 'pythonint311'
        elif __sysversion_info.minor==12:
            __irispythonint = 'pythonint312'
        elif __sysversion_info.minor==13:
            __irispythonint = 'pythonint313'
        elif __sysversion_info.minor==14:
            __irispythonint = 'pythonint314'
    else:
        __irispythonint = 'pythonint'

    if __irispythonint is not None:
        try:
        # try to import the pythonint module
            try:
                __iris_module = importlib.import_module(name=__irispythonint)
            except ModuleNotFoundError:
                __irispythonint = 'pythonint'
                __iris_module = importlib.import_module(name=__irispythonint)
            globals().update(__iris_module.__dict__)
        except ImportError as e:
            logging.warning("Error importing %s: %s", __irispythonint, e)
            logging.warning("Embedded Python not available")
            
            def __getattr__(name):
                current_runtime = _runtime_manager.get()
                if current_runtime.mode == 'native':
                    if current_runtime.iris is None:
                        raise RuntimeError(
                            "iris.runtime is configured for native mode, but no native IRIS handle is bound"
                        )
                    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
                if current_runtime.mode == 'embedded':
                    raise RuntimeError(
                        "iris.runtime is configured for embedded mode, but embedded Python is unavailable"
                    )
                if current_runtime.iris is not None:
                    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
                    
                if name == "__all__":
                    return []
                logging.warning(f"Class or module '{name}' not found in iris_embedded_python. Returning a mock object. Make sure you local installation is correct.")
                from unittest.mock import MagicMock
                return MagicMock()
        

# Wrap the 'cls' function to support Native API when Embedded Python isn't available
_original_cls = globals().get('cls')

def cls(class_name):
    current_runtime = _runtime_manager.get()
    if current_runtime.mode == 'native':
        if current_runtime.iris is None:
            raise RuntimeError("iris.runtime is configured for native mode, but no native IRIS handle is bound")
        return NativeClassProxy(class_name, current_runtime.iris)
    if current_runtime.mode == 'embedded':
        if _original_cls is None:
            raise RuntimeError("iris.runtime is configured for embedded mode, but embedded Python is unavailable")
        return _original_cls(class_name)
    if current_runtime.embedded_available and _original_cls is not None:
        return _original_cls(class_name)
    if current_runtime.iris is not None:
        return NativeClassProxy(class_name, current_runtime.iris)
    logging.warning("No Embedded Python or Native API connection available.")
    from unittest.mock import MagicMock
    return MagicMock()


class _RuntimeNamespace:
    @property
    def state(self):
        return _runtime_manager.get().state

    @property
    def mode(self):
        return _runtime_manager.get().mode

    @property
    def embedded_available(self):
        return _runtime_manager.get().embedded_available

    @property
    def iris(self):
        return _runtime_manager.get().iris

    @property
    def dbapi(self):
        return _runtime_manager.get().dbapi

    @property
    def native_connection(self):
        return _runtime_manager.get().native_connection

    def get(self):
        return _runtime_manager.get()

    def configure(self, **kwargs):
        return _runtime_manager.configure(**kwargs)

    def reset(self):
        return _runtime_manager.reset()


runtime = _RuntimeNamespace()

# Expose DB-API facade. It defaults to embedded SQL in auto mode, and can
# delegate to native DB-API when remote parameters are provided.
dbapi = make_dbapi(_runtime_manager, lambda: globals().get('sql'))
        
# restore working directory
os.chdir(__ospath)

