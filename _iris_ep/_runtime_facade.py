from __future__ import annotations

import logging
import sys
import warnings
from typing import Any

from iris_utils import NativeClassProxy, runtime as _runtime_manager

from . import _bootstrap
from ._dbapi import make_dbapi

_WRAPPER_EXPORTS = {"_runtime", "runtime", "dbapi", "cls", "connect"}


def copy_public_exports(module: Any, module_globals: dict[str, Any], skip=()) -> None:
    skipped = set(skip)
    exported_names = getattr(module, "__all__", None)
    if exported_names is None:
        exported_names = [name for name in module.__dict__ if not name.startswith("_")]

    for name in exported_names:
        if name in skipped:
            continue
        module_globals[name] = getattr(module, name)

    if hasattr(module, "__getattr__"):
        module_globals["__getattr__"] = getattr(module, "__getattr__")


def install_unavailable_getattr(module_globals: dict[str, Any], module_name: str) -> None:
    def __getattr__(name):
        if name == "__all__":
            return []
        if name.startswith("_"):
            raise AttributeError(f"module '{module_name}' has no attribute '{name}'")

        current_runtime = _runtime_manager.get()
        if current_runtime.mode == 'native':
            if current_runtime.iris is None:
                raise RuntimeError(
                    "iris.runtime is configured for native mode, but no native IRIS handle is bound"
                )
            raise AttributeError(f"module '{module_name}' has no attribute '{name}'")
        if current_runtime.mode == 'embedded':
            raise RuntimeError(
                "iris.runtime is configured for embedded mode, but embedded Python is unavailable"
            )
        if current_runtime.iris is not None:
            raise AttributeError(f"module '{module_name}' has no attribute '{name}'")

        logging.warning(
            "Class or module '%s' not found in iris_embedded_python. "
            "Returning a mock object. Make sure you local installation is correct.",
            name,
        )
        from unittest.mock import MagicMock
        return MagicMock()

    module_globals["__getattr__"] = __getattr__


def install_default_getattr(module_globals: dict[str, Any], module_name: str) -> None:
    def __getattr__(name):
        if name == "__all__":
            return []
        raise AttributeError(f"module '{module_name}' has no attribute '{name}'")

    module_globals["__getattr__"] = __getattr__


class EmbeddedSystemProxy:
    def __init__(self, facade: "RuntimeFacade"):
        self._facade = facade

    def __getattr__(self, name):
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")
        mapped_name = name.replace("_", "%", 1) if name.startswith("_") else name
        return self._facade.cls(f"%SYSTEM.{mapped_name}")


class RuntimeNamespace:
    def __init__(self, facade: "RuntimeFacade"):
        self._facade = facade

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
        has_iris_shape = RuntimeNamespace._is_native_iris_handle(candidate)
        return has_connection_shape and not has_iris_shape

    def _convert_connection_to_iris(self, connection):
        if self._is_native_iris_handle(connection):
            return connection

        create_iris = self._facade.module_globals.get("createIRIS")
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

    def load_embedded_backend(self, path):
        return self._facade.load_embedded_backend(path)

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


class RuntimeFacade:
    def __init__(
        self,
        module_globals: dict[str, Any],
        module_name: str,
        runtime_manager: Any = _runtime_manager,
    ):
        self.module_globals = module_globals
        self.module_name = module_name
        self.runtime_manager = runtime_manager
        self.runtime = RuntimeNamespace(self)
        self.dbapi = make_dbapi(self.runtime, self.get_dbapi_embedded_cls)
        self._public_cls = None
        self._public_connect = None

    def configure_from_environment(self) -> None:
        installdir = _bootstrap.get_install_dir_from_env()
        self.runtime_manager.configure(install_dir=installdir)

        if _bootstrap.is_embedded_kernel():
            module = _bootstrap.import_embedded_kernel_module()
            self.install_embedded_module(module)
            return

        if installdir is None:
            logging.warning("IRISINSTALLDIR or ISC_PACKAGE_INSTALLDIR environment variable is not set")
            logging.warning("Embedded Python not configured; call iris.connect(path=...) to configure it")
        else:
            _bootstrap.configure_install_dir(
                installdir,
                warn_loader_path=not _bootstrap.is_embedded_kernel(),
            )

        pythonint_module_name = (
            _bootstrap.get_pythonint_module_name() if installdir is not None else None
        )
        if pythonint_module_name is None:
            install_unavailable_getattr(self.module_globals, self.module_name)
            return

        try:
            module = _bootstrap.import_pythonint_module(pythonint_module_name)
        except ImportError as exc:
            logging.warning("Error importing %s: %s", pythonint_module_name, exc)
            logging.warning("Embedded Python not available")
            install_unavailable_getattr(self.module_globals, self.module_name)
            return

        self.install_embedded_module(module)

    def install_public_symbols(self) -> None:
        def public_cls(class_name):
            return self.cls(class_name)

        def public_connect(*args, path=None, **kwargs):
            return self.connect(*args, path=path, **kwargs)

        public_cls.__name__ = "cls"
        public_connect.__name__ = "connect"
        self._public_cls = public_cls
        self._public_connect = public_connect

        self.module_globals["_runtime"] = self.runtime
        self.module_globals["runtime"] = self.runtime
        self.module_globals["dbapi"] = self.dbapi
        self.module_globals["cls"] = public_cls
        self.module_globals["connect"] = public_connect

    def finalize_all(self) -> None:
        existing_all = self.module_globals.get("__all__")
        if isinstance(existing_all, (list, tuple, set)):
            exported_names = [str(name) for name in existing_all]
        else:
            exported_names = [
                name for name in self.module_globals
                if not name.startswith("_")
            ]

        for name in ("runtime", "dbapi", "cls", "connect"):
            if name not in exported_names:
                exported_names.append(name)

        self.module_globals["__all__"] = exported_names

    def bind_embedded_backend(self, module: Any):
        embedded_cls = getattr(module, 'cls', None)
        embedded_connect = getattr(module, 'connect', None)
        return self.runtime_manager.bind_backends(
            embedded_module=module,
            embedded_cls=embedded_cls,
            embedded_connect=embedded_connect,
        )

    def install_embedded_module(self, module: Any):
        module_getattr = getattr(module, "__getattr__", None)
        copy_public_exports(module, self.module_globals, skip=_WRAPPER_EXPORTS)
        self.install_embedded_convenience_symbols(module)
        if callable(module_getattr):
            self.module_globals["__getattr__"] = module_getattr
        else:
            install_default_getattr(self.module_globals, self.module_name)

        context = self.bind_embedded_backend(module)
        self.sync_public_modules()
        return context

    def install_embedded_convenience_symbols(self, module: Any):
        # Some embedded kernel modules resolve unknown package names through
        # __getattr__ and return an iris.package placeholder.  Keep
        # iris.system.* routed through cls("%SYSTEM.*") so convenience calls
        # such as iris.system.Version.GetVersion() behave like class access.
        self.module_globals["system"] = EmbeddedSystemProxy(self)

        if hasattr(module, "sql"):
            self.module_globals["sql"] = getattr(module, "sql")

        exported_names = self.module_globals.get("__all__")
        if isinstance(exported_names, list):
            for name in ("system",):
                if name in self.module_globals and name not in exported_names:
                    exported_names.append(name)

    def sync_public_modules(self):
        public_names = set()
        exported_names = self.module_globals.get("__all__")
        if isinstance(exported_names, (list, tuple, set)):
            public_names.update(str(name) for name in exported_names)
        public_names.update(("runtime", "dbapi", "cls", "connect", "system"))

        for module_name in ("iris", "iris_ep", "iris_embedded_python"):
            module = sys.modules.get(module_name)
            if module is None:
                continue
            for name in public_names:
                if name in self.module_globals:
                    setattr(module, name, self.module_globals[name])
            if "__getattr__" in self.module_globals:
                setattr(module, "__getattr__", self.module_globals["__getattr__"])

    def load_embedded_backend(self, path):
        install_dir = _bootstrap.configure_install_dir(path, warn_loader_path=True)
        module = _bootstrap.import_pythonint_module_from_install_dir(install_dir)
        self.install_embedded_module(module)
        return self.runtime_manager.configure(mode='embedded', install_dir=install_dir)

    def ensure_embedded_backend(self, current_runtime=None, required=False):
        current_runtime = current_runtime or self.runtime_manager.get()
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

        self.install_embedded_module(module)
        return self.runtime_manager.get()

    def get_embedded_cls(self, current_runtime=None, required=False):
        current_runtime = self.ensure_embedded_backend(current_runtime, required=required)
        embedded_cls = getattr(current_runtime, "embedded_cls", None)
        return embedded_cls if callable(embedded_cls) else None

    def get_embedded_connect(self, current_runtime=None, required=False):
        current_runtime = self.ensure_embedded_backend(current_runtime, required=required)
        embedded_connect = getattr(current_runtime, "embedded_connect", None)
        return embedded_connect if callable(embedded_connect) else None

    def get_dbapi_embedded_cls(self):
        embedded_cls = self.get_embedded_cls(self.runtime.get())
        if callable(embedded_cls):
            return embedded_cls

        cls_candidate = self.module_globals.get("cls")
        if callable(cls_candidate) and cls_candidate is not self._public_cls:
            return cls_candidate
        return None

    def cls(self, class_name):
        current_runtime = self.runtime_manager.get()
        if current_runtime.mode == 'native':
            if current_runtime.iris is None:
                raise RuntimeError("iris.runtime is configured for native mode, but no native IRIS handle is bound")
            return NativeClassProxy(class_name, current_runtime.iris)
        if current_runtime.mode == 'embedded':
            embedded_cls = self.get_embedded_cls(current_runtime, required=True)
            if embedded_cls is None:
                raise RuntimeError("iris.runtime is configured for embedded mode, but embedded Python is unavailable")
            return embedded_cls(class_name)
        if current_runtime.embedded_available:
            embedded_cls = self.get_embedded_cls(current_runtime)
            if embedded_cls is not None:
                return embedded_cls(class_name)
        if current_runtime.iris is not None:
            return NativeClassProxy(class_name, current_runtime.iris)
        logging.warning("No Embedded Python or Native API connection available.")
        from unittest.mock import MagicMock
        return MagicMock()

    def connect(self, *args, path=None, **kwargs):
        if path is not None:
            if args or kwargs:
                raise TypeError("iris.connect(path=...) cannot be combined with native connection arguments")
            context = self.load_embedded_backend(path)
            if not callable(getattr(context, "embedded_connect", None)):
                warnings.warn(
                    "iris.connect(path=...) configured embedded runtime and returned "
                    "a RuntimeContext, not a DB-API connection. The embedded backend "
                    "does not expose connect(); use iris.dbapi.connect(path=...) for "
                    "a DB-API connection or iris.cls(...) for embedded class access.",
                    RuntimeWarning,
                    stacklevel=2,
                )
            return context

        current_runtime = self.runtime_manager.get()
        if current_runtime.mode == 'embedded':
            embedded_connect = self.get_embedded_connect(current_runtime, required=True)
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

        embedded_connect = self.get_embedded_connect(current_runtime)
        if callable(embedded_connect):
            return embedded_connect(*args, **kwargs)

        raise RuntimeError("iris.connect requires path=... for embedded mode or an installed native driver")


def initialize_module(module_globals: dict[str, Any], module_name: str) -> RuntimeFacade:
    facade = RuntimeFacade(module_globals, module_name)
    facade.configure_from_environment()
    if "__getattr__" not in module_globals:
        install_default_getattr(module_globals, module_name)
    facade.install_public_symbols()
    facade.finalize_all()
    facade.sync_public_modules()
    return facade
