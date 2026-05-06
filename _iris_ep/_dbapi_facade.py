from __future__ import annotations

from typing import Any, Optional

from . import _dbapi_native
from ._dbapi_embedded import _DEFAULT_ISOLATION_LEVEL, _EmbeddedConnection
from ._dbapi_exceptions import (
    Binary,
    DataError,
    DatabaseError,
    Error,
    IntegrityError,
    InterfaceError,
    InternalError,
    NotSupportedError,
    OperationalError,
    ProgrammingError,
    Warning,
    apilevel,
    paramstyle,
    threadsafety,
)


class _DBAPI:
    def __init__(self, runtime_manager: Any, cls_getter: Any = None):
        self._runtime_manager = runtime_manager
        self._cls_getter = cls_getter

        # PEP 249 module-level attributes
        self.apilevel = apilevel
        self.threadsafety = threadsafety
        self.paramstyle = paramstyle

        # PEP 249 exception hierarchy
        self.Warning = Warning
        self.Error = Error
        self.InterfaceError = InterfaceError
        self.DatabaseError = DatabaseError
        self.DataError = DataError
        self.OperationalError = OperationalError
        self.IntegrityError = IntegrityError
        self.InternalError = InternalError
        self.ProgrammingError = ProgrammingError
        self.NotSupportedError = NotSupportedError
        self.Binary = Binary

    def connect(
        self,
        *args,
        mode: str = "auto",
        isolation_level: Optional[str] = _DEFAULT_ISOLATION_LEVEL,
        **kwargs,
    ):
        has_namespace_arg = "namespace" in kwargs
        has_native_remote_args = bool(args) or any(
            key in kwargs
            for key in (
                "hostname",
                "port",
                "username",
                "password",
                "connectionstr",
                "accessToken",
            )
        )
        has_remote_args = has_native_remote_args or has_namespace_arg

        if mode not in ("auto", "embedded", "native"):
            raise InterfaceError(f"Unsupported dbapi mode: {mode}")

        if mode == "auto" and has_namespace_arg and not has_native_remote_args:
            raise InterfaceError(
                "DB-API auto mode cannot infer whether namespace=... is for embedded or native; "
                "pass mode='embedded' or provide native connection arguments"
            )

        if mode == "native" or (mode == "auto" and has_remote_args):
            return self._connect_native(*args, **kwargs)

        runtime_state = self._runtime_manager.get()

        if mode == "auto" and runtime_state.dbapi is not None:
            return runtime_state.dbapi

        if mode == "auto" and runtime_state.mode == "native":
            raise InterfaceError(
                "DB-API auto mode cannot infer a native DB-API connection from iris.runtime native bindings alone; "
                "pass native connection arguments or bind a DB-API connection with iris.runtime.configure(dbapi=...)"
            )

        if mode in ("embedded", "auto"):
            if not runtime_state.embedded_available or runtime_state.state not in (
                "embedded-kernel",
                "embedded-local",
            ):
                raise InterfaceError(
                    "Embedded DB-API is only available in embedded runtime (embedded-kernel or embedded-local) via %SQL.Statement"
                )
            return _EmbeddedConnection(
                self._get_embedded_cls,
                use_statement=True,
                isolation_level=isolation_level,
                namespace=kwargs.pop("namespace", None),
            )

        raise InterfaceError(f"Unsupported dbapi mode: {mode}")

    def _connect_native(self, *args, **kwargs):
        runtime_peek = getattr(self._runtime_manager, "peek", None)
        runtime_state = runtime_peek() if callable(runtime_peek) else self._runtime_manager.get()
        native_dbapi = getattr(runtime_state, "native_dbapi_module", None)
        if native_dbapi is None:
            try:
                native_dbapi = self._import_native_dbapi()
            except ImportError as exc:
                raise InterfaceError(
                    "Official native DB-API driver is unavailable (expected module: iris.dbapi)"
                ) from exc
            bind_backends = getattr(self._runtime_manager, "bind_backends", None)
            if callable(bind_backends):
                bind_backends(native_dbapi_module=native_dbapi)

        self._restore_public_facade(native_dbapi)

        if not hasattr(native_dbapi, "connect"):
            raise InterfaceError("Official native DB-API driver is invalid: missing connect()")

        return native_dbapi.connect(*args, **kwargs)

    def _get_embedded_cls(self):
        runtime_state = self._runtime_manager.get()
        embedded_cls = getattr(runtime_state, "embedded_cls", None)
        if callable(embedded_cls):
            return embedded_cls
        if self._cls_getter is not None:
            return self._cls_getter()
        return None

    @staticmethod
    def _import_native_dbapi():
        return _dbapi_native.import_native_dbapi()

    @staticmethod
    def _import_native_dbapi_from_distribution():
        return _dbapi_native.import_native_dbapi_from_distribution()

    @staticmethod
    def _load_official_iris_package(package_init, package_dir):
        return _dbapi_native.load_official_iris_package(package_init, package_dir)

    @staticmethod
    def _attach_official_iris_sdk(public_iris: Any, official_iris: Any, package_dir):
        return _dbapi_native.attach_official_iris_sdk(public_iris, official_iris, package_dir)

    def _restore_public_facade(self, native_dbapi: Any):
        return _dbapi_native.restore_public_facade(native_dbapi, self)


def make_dbapi(runtime_manager: Any, cls_getter: Any = None) -> _DBAPI:
    return _DBAPI(runtime_manager=runtime_manager, cls_getter=cls_getter)
