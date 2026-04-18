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
    @staticmethod
    def _is_native_iris_handle(candidate):
        if candidate is None:
            return False
        return hasattr(candidate, "classMethodValue") or hasattr(candidate, "invokeClassMethod")

    @staticmethod
    def _is_native_connection(candidate):
        if candidate is None:
            return False
        has_connection_shape = hasattr(candidate, "isConnected")
        has_iris_shape = _RuntimeNamespace._is_native_iris_handle(candidate)
        return has_connection_shape and not has_iris_shape

    @staticmethod
    def _convert_connection_to_iris(connection):
        if _RuntimeNamespace._is_native_iris_handle(connection):
            return connection

        create_iris = globals().get("createIRIS")
        if not callable(create_iris):
            try:
                import iris as iris_module
                create_iris = getattr(iris_module, "createIRIS", None)
            except Exception:
                create_iris = None

        if not callable(create_iris):
            raise RuntimeError(
                "runtime.configure received an IRISConnection, but createIRIS() is unavailable"
            )
        iris_handle = create_iris(connection)
        if iris_handle is None:
            raise RuntimeError(
                "runtime.configure could not convert IRISConnection to an IRIS handle via createIRIS()"
            )
        return iris_handle

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
        config = dict(kwargs)

        # If a native connection is provided, normalize it to an IRIS handle.
        native_connection = config.get("native_connection")
        if config.get("iris") is None and native_connection is not None:
            if self._is_native_iris_handle(native_connection):
                config["iris"] = native_connection
            else:
                config["iris"] = self._convert_connection_to_iris(native_connection)

        # Accept connection-like objects passed as the "iris" argument and normalize them.
        if config.get("iris") is not None and not self._is_native_iris_handle(config.get("iris")):
            config["native_connection"] = config.get("native_connection") or config["iris"]
            config["iris"] = self._convert_connection_to_iris(config["iris"])

        # Infer native mode when caller binds explicit native/dbapi handles.
        if "mode" not in config and (
            config.get("iris") is not None
            or config.get("native_connection") is not None
            or config.get("dbapi") is not None
        ):
            config["mode"] = "native"

        if config.get("mode") == "native" and config.get("iris") is None and config.get("dbapi") is None:
            raise RuntimeError(
                "runtime.configure in native mode requires a valid IRIS handle, a convertible IRISConnection, or dbapi connection"
            )

        return _runtime_manager.configure(**config)

    def reset(self):
        return _runtime_manager.reset()


runtime = _RuntimeNamespace()

# Expose DB-API facade. It defaults to embedded SQL in auto mode, and can
# delegate to native DB-API when remote parameters are provided.
dbapi = make_dbapi(
    _runtime_manager,
    lambda: globals().get('cls'),
)
        
# restore working directory
os.chdir(__ospath)

