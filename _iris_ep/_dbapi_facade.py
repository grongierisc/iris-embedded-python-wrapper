from __future__ import annotations

from typing import Any, Optional

from . import _dbapi_native
from ._dbapi_embedded import (
    _DEFAULT_ISOLATION_LEVEL,
    _EmbeddedConnection,
)
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

_NATIVE_REMOTE_ARGUMENTS = (
    "hostname",
    "port",
    "username",
    "password",
    "connectionstr",
    "accessToken",
)

_NATIVE_EXCEPTION_TRANSLATIONS = (
    ("InterfaceError", InterfaceError),
    ("DataError", DataError),
    ("OperationalError", OperationalError),
    ("IntegrityError", IntegrityError),
    ("InternalError", InternalError),
    ("ProgrammingError", ProgrammingError),
    ("NotSupportedError", NotSupportedError),
    ("DatabaseError", DatabaseError),
    ("Error", Error),
    ("Warning", Warning),
)


def _translate_native_exception(native_dbapi: Any, exc: Exception) -> Exception:
    if isinstance(exc, Error):
        return exc

    for name, wrapper_cls in _NATIVE_EXCEPTION_TRANSLATIONS:
        native_cls = getattr(native_dbapi, name, None)
        if not isinstance(native_cls, type) or not isinstance(exc, native_cls):
            continue

        translated = wrapper_cls(*getattr(exc, "args", ()))
        try:
            translated.__dict__.update(getattr(exc, "__dict__", {}))
        except Exception:
            pass
        return translated

    return exc


def _call_native(native_dbapi: Any, fn: Any, *args: Any, **kwargs: Any):
    try:
        return fn(*args, **kwargs)
    except Exception as exc:
        translated = _translate_native_exception(native_dbapi, exc)
        if translated is exc:
            raise
        raise translated from exc


class _NativeProxy:
    def __init__(self, target: Any, native_dbapi: Any):
        object.__setattr__(self, "_target", target)
        object.__setattr__(self, "_native_dbapi", native_dbapi)

    def __getattr__(self, name: str):
        attr = getattr(self._target, name)
        if callable(attr):

            def wrapped(*args: Any, **kwargs: Any):
                return _call_native(self._native_dbapi, attr, *args, **kwargs)

            return wrapped
        return attr

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_"):
            object.__setattr__(self, name, value)
            return
        setattr(self._target, name, value)


class _NativeConnectionProxy(_NativeProxy):
    def cursor(self, *args: Any, **kwargs: Any):
        cursor = _call_native(self._native_dbapi, self._target.cursor, *args, **kwargs)
        return _NativeCursorProxy(cursor, self._native_dbapi)

    def commit(self):
        return _call_native(self._native_dbapi, self._target.commit)

    def rollback(self):
        return _call_native(self._native_dbapi, self._target.rollback)

    def close(self):
        return _call_native(self._native_dbapi, self._target.close)

    def __enter__(self):
        result = _call_native(self._native_dbapi, self._target.__enter__)
        return self if result is self._target else result

    def __exit__(self, exc_type, exc_value, traceback):
        return _call_native(
            self._native_dbapi,
            self._target.__exit__,
            exc_type,
            exc_value,
            traceback,
        )


class _NativeCursorProxy(_NativeProxy):
    def execute(self, *args: Any, **kwargs: Any):
        result = _call_native(self._native_dbapi, self._target.execute, *args, **kwargs)
        return self if result is self._target else result

    def executemany(self, *args: Any, **kwargs: Any):
        result = _call_native(self._native_dbapi, self._target.executemany, *args, **kwargs)
        return self if result is self._target else result

    def fetchone(self):
        return _call_native(self._native_dbapi, self._target.fetchone)

    def fetchmany(self, *args: Any, **kwargs: Any):
        return _call_native(self._native_dbapi, self._target.fetchmany, *args, **kwargs)

    def fetchall(self):
        return _call_native(self._native_dbapi, self._target.fetchall)

    def close(self):
        return _call_native(self._native_dbapi, self._target.close)

    def __iter__(self):
        return self

    def __next__(self):
        return _call_native(self._native_dbapi, self._target.__next__)

    def __enter__(self):
        result = _call_native(self._native_dbapi, self._target.__enter__)
        return self if result is self._target else result

    def __exit__(self, exc_type, exc_value, traceback):
        return _call_native(
            self._native_dbapi,
            self._target.__exit__,
            exc_type,
            exc_value,
            traceback,
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
        path: Any = None,
        mode: str = "auto",
        isolation_level: Optional[str] = _DEFAULT_ISOLATION_LEVEL,
        **kwargs,
    ):
        has_namespace_arg = "namespace" in kwargs
        has_native_remote_args = bool(args) or any(
            key in kwargs for key in _NATIVE_REMOTE_ARGUMENTS
        )
        has_remote_args = has_native_remote_args or has_namespace_arg

        if mode not in ("auto", "embedded", "native"):
            raise InterfaceError(f"Unsupported dbapi mode: {mode}")

        if path is not None:
            return self._connect_embedded_path(
                path=path,
                args=args,
                kwargs=kwargs,
                mode=mode,
                has_native_remote_args=has_native_remote_args,
                isolation_level=isolation_level,
            )

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
            return self._connect_embedded(
                runtime_state,
                isolation_level=isolation_level,
                namespace=kwargs.pop("namespace", None),
            )

        raise InterfaceError(f"Unsupported dbapi mode: {mode}")

    def _connect_embedded_path(
        self,
        *,
        path: Any,
        args: Any,
        kwargs: dict[str, Any],
        mode: str,
        has_native_remote_args: bool,
        isolation_level: Optional[str],
    ):
        if mode == "native":
            raise InterfaceError(
                "iris.dbapi.connect(path=...) requires mode='auto' or mode='embedded'"
            )
        if has_native_remote_args:
            raise InterfaceError(
                "iris.dbapi.connect(path=...) cannot be combined with native connection arguments"
            )

        namespace = kwargs.pop("namespace", None)
        if kwargs:
            supported = "namespace"
            received = ", ".join(sorted(kwargs))
            raise InterfaceError(
                f"iris.dbapi.connect(path=...) only accepts embedded options ({supported}); "
                f"got: {received}"
            )

        load_embedded_backend = getattr(self._runtime_manager, "load_embedded_backend", None)
        if not callable(load_embedded_backend):
            raise InterfaceError(
                "iris.dbapi.connect(path=...) requires the iris runtime facade"
            )

        try:
            runtime_state = load_embedded_backend(path)
        except Exception as exc:
            raise InterfaceError(
                f"iris.dbapi.connect(path=...) could not configure embedded runtime: {exc}"
            ) from exc

        return self._connect_embedded(
            runtime_state,
            isolation_level=isolation_level,
            namespace=namespace,
        )

    def _connect_embedded(
        self,
        runtime_state: Any,
        *,
        isolation_level: Optional[str],
        namespace: Optional[str],
    ):
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
            namespace=namespace,
        )

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

        connection = _call_native(native_dbapi, native_dbapi.connect, *args, **kwargs)
        if hasattr(connection, "cursor"):
            return _NativeConnectionProxy(connection, native_dbapi)
        return connection

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
