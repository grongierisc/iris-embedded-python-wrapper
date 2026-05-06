import os
import logging

logging.basicConfig(level=logging.INFO)

from .iris_ipm import ipm
from ._dbapi import make_dbapi
from . import _bootstrap
from iris_utils import NativeClassProxy, runtime as _runtime_manager


def _copy_public_exports(module):
    exported_names = getattr(module, "__all__", None)
    if exported_names is None:
        exported_names = [name for name in module.__dict__ if not name.startswith("_")]

    for name in exported_names:
        globals()[name] = getattr(module, name)

    if hasattr(module, "__getattr__"):
        globals()["__getattr__"] = getattr(module, "__getattr__")


def _install_unavailable_getattr():
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
        logging.warning(
            "Class or module '%s' not found in iris_embedded_python. "
            "Returning a mock object. Make sure you local installation is correct.",
            name,
        )
        from unittest.mock import MagicMock
        return MagicMock()

    globals()["__getattr__"] = __getattr__


def _bind_embedded_backend(module):
    embedded_cls = getattr(module, 'cls', None)
    embedded_connect = getattr(module, 'connect', None)
    return _runtime_manager.bind_backends(
        embedded_module=module,
        embedded_cls=embedded_cls,
        embedded_connect=embedded_connect,
    )


# check for install dir in environment
# environment to check is IRISINSTALLDIR
# if not found, raise exception and exit
# ISC_PACKAGE_INSTALLDIR - defined by default in Docker images
installdir = _bootstrap.get_install_dir_from_env()

_runtime_manager.configure(install_dir=installdir)

if installdir is None:
    logging.warning("IRISINSTALLDIR or ISC_PACKAGE_INSTALLDIR environment variable is not set")
    logging.warning("Embedded Python not configured; call iris.connect(path=...) to configure it")
else:
    _bootstrap.configure_install_dir(installdir)

# save working directory
__ospath = os.getcwd()

if _bootstrap.is_embedded_kernel():
    # python(libpython.so) inside iris
    __iris_module = _bootstrap.import_embedded_kernel_module()
    _copy_public_exports(__iris_module)
else:

    __irispythonint = _bootstrap.get_pythonint_module_name() if installdir is not None else None

    if __irispythonint is not None:
        try:
            # try to import the pythonint module
            __iris_module = _bootstrap.import_pythonint_module(__irispythonint)
            globals().update(__iris_module.__dict__)
        except ImportError as e:
            logging.warning("Error importing %s: %s", __irispythonint, e)
            logging.warning("Embedded Python not available")
            _install_unavailable_getattr()
    else:
        _install_unavailable_getattr()
        

# Wrap the 'cls' function to support Native API when Embedded Python isn't available
_original_cls = globals().get('cls')
_original_connect = globals().get('connect')
_fallback_connect = None

if "__iris_module" in globals():
    _bind_embedded_backend(globals()["__iris_module"])

def _install_embedded_module(module):
    global _original_cls, _original_connect

    wrapper_cls = globals().get('cls')
    wrapper_connect = globals().get('connect')
    runtime_obj = globals().get('runtime')
    dbapi_obj = globals().get('dbapi')
    embedded_cls = getattr(module, 'cls', None)
    embedded_connect = getattr(module, 'connect', None)

    globals().update(module.__dict__)
    _original_cls = embedded_cls
    _original_connect = embedded_connect
    _bind_embedded_backend(module)

    if callable(wrapper_cls):
        globals()['cls'] = wrapper_cls
    if callable(wrapper_connect):
        globals()['connect'] = wrapper_connect
    if runtime_obj is not None:
        globals()['runtime'] = runtime_obj
    if dbapi_obj is not None:
        globals()['dbapi'] = dbapi_obj


def _load_embedded_backend(path):
    install_dir = _bootstrap.configure_install_dir(path)
    module = _bootstrap.import_pythonint_module()
    _install_embedded_module(module)
    return _runtime_manager.configure(mode='embedded', install_dir=install_dir)

def _ensure_embedded_backend(current_runtime=None, required=False):
    current_runtime = current_runtime or _runtime_manager.get()
    if not hasattr(current_runtime, "embedded_cls"):
        return current_runtime
    if callable(getattr(current_runtime, "embedded_cls", None)) or callable(
        getattr(current_runtime, "embedded_connect", None)
    ):
        return current_runtime

    try:
        if _bootstrap.is_embedded_kernel():
            module = _bootstrap.import_embedded_kernel_module()
        else:
            install_dir = getattr(current_runtime, "install_dir", None)
            if install_dir is None:
                install_dir = _bootstrap.get_install_dir_from_env()
            if install_dir is None:
                raise RuntimeError(
                    "Embedded Python is unavailable; configure IRISINSTALLDIR or call iris.connect(path=...)"
                )
            _bootstrap.configure_install_dir(install_dir)
            module = _bootstrap.import_pythonint_module()
    except Exception:
        if required:
            raise
        return current_runtime

    _install_embedded_module(module)
    return _runtime_manager.get()


def _get_embedded_cls(current_runtime=None, required=False):
    current_runtime = _ensure_embedded_backend(current_runtime, required=required)
    embedded_cls = getattr(current_runtime, "embedded_cls", None)
    return embedded_cls if callable(embedded_cls) else None


def _get_embedded_connect(current_runtime=None, required=False):
    current_runtime = _ensure_embedded_backend(current_runtime, required=required)
    embedded_connect = getattr(current_runtime, "embedded_connect", None)
    return embedded_connect if callable(embedded_connect) else None


def cls(class_name):
    current_runtime = _runtime_manager.get()
    if current_runtime.mode == 'native':
        if current_runtime.iris is None:
            raise RuntimeError("iris.runtime is configured for native mode, but no native IRIS handle is bound")
        return NativeClassProxy(class_name, current_runtime.iris)
    if current_runtime.mode == 'embedded':
        embedded_cls = _get_embedded_cls(current_runtime, required=True)
        if embedded_cls is None:
            raise RuntimeError("iris.runtime is configured for embedded mode, but embedded Python is unavailable")
        return embedded_cls(class_name)
    if current_runtime.embedded_available:
        embedded_cls = _get_embedded_cls(current_runtime)
        if embedded_cls is not None:
            return embedded_cls(class_name)
    if current_runtime.iris is not None:
        return NativeClassProxy(class_name, current_runtime.iris)
    logging.warning("No Embedded Python or Native API connection available.")
    from unittest.mock import MagicMock
    return MagicMock()


def connect(*args, path=None, **kwargs):
    if path is not None:
        if args or kwargs:
            raise TypeError("iris.connect(path=...) cannot be combined with native connection arguments")
        return _load_embedded_backend(path)

    current_runtime = _runtime_manager.get()
    if current_runtime.mode == 'embedded':
        embedded_connect = _get_embedded_connect(current_runtime, required=True)
        if callable(embedded_connect):
            return embedded_connect(*args, **kwargs)
        raise RuntimeError("iris.connect requires an embedded runtime backend")

    if current_runtime.mode == 'native':
        native_connect = getattr(current_runtime, "native_connect", None)
        if callable(native_connect):
            return native_connect(*args, **kwargs)
        raise RuntimeError("iris.connect requires an installed native driver")

    native_connect = getattr(current_runtime, "native_connect", None)
    if callable(native_connect):
        return native_connect(*args, **kwargs)

    embedded_connect = _get_embedded_connect(current_runtime)
    if callable(embedded_connect):
        return embedded_connect(*args, **kwargs)

    raise RuntimeError("iris.connect requires path=... for embedded mode or an installed native driver")


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
    def embedded_module(self):
        return _runtime_manager.get().embedded_module

    @property
    def embedded_cls(self):
        return _runtime_manager.get().embedded_cls

    @property
    def embedded_connect(self):
        return _runtime_manager.get().embedded_connect

    @property
    def iris(self):
        return _runtime_manager.get().iris

    @property
    def dbapi(self):
        return _runtime_manager.get().dbapi

    @property
    def native_connection(self):
        return _runtime_manager.get().native_connection

    @property
    def native_connect(self):
        return _runtime_manager.get().native_connect

    @property
    def native_dbapi_module(self):
        return _runtime_manager.get().native_dbapi_module

    def get(self):
        return _runtime_manager.get()

    def peek(self):
        return _runtime_manager.peek()

    def bind_backends(self, **kwargs):
        return _runtime_manager.bind_backends(**kwargs)

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


_runtime = _RuntimeNamespace()
runtime = _runtime

# Expose DB-API facade. It defaults to embedded SQL in auto mode, and can
# delegate to native DB-API when remote parameters are provided.
dbapi = make_dbapi(
    _runtime,
    lambda: _get_embedded_cls(_runtime.get()) or globals().get('cls'),
)

_existing_all = globals().get("__all__")
if isinstance(_existing_all, (list, tuple, set)):
    _exported_names = [str(name) for name in _existing_all]
else:
    _exported_names = [name for name in globals() if not name.startswith("_")]

for _name in ("runtime", "dbapi", "cls", "connect"):
    if _name not in _exported_names:
        _exported_names.append(_name)

globals()["__all__"] = _exported_names
        
# restore working directory
os.chdir(__ospath)
