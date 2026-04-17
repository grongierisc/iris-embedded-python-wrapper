from __future__ import annotations

from collections.abc import Iterable
import importlib
from typing import Any, Optional


apilevel = "2.0"
threadsafety = 1
paramstyle = "qmark"


class Warning(Exception):
    """Exception raised for important warnings."""


class Error(Exception):
    """Base class for DB-API exceptions."""


class InterfaceError(Error):
    """Exception raised for interface-related errors."""


class DatabaseError(Error):
    """Exception raised for database-related errors."""


class DataError(DatabaseError):
    pass


class OperationalError(DatabaseError):
    pass


class IntegrityError(DatabaseError):
    pass


class InternalError(DatabaseError):
    pass


class ProgrammingError(DatabaseError):
    pass


class NotSupportedError(DatabaseError):
    pass


class _EmbeddedConnection:
    def __init__(self, sql_api: Any):
        if sql_api is None:
            raise InterfaceError("Embedded SQL API is unavailable")
        self._sql = sql_api
        self._closed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def cursor(self):
        if self._closed:
            raise InterfaceError("Connection is closed")
        return _EmbeddedCursor(self)

    def close(self):
        self._closed = True

    def commit(self):
        if self._closed:
            raise InterfaceError("Connection is closed")

    def rollback(self):
        if self._closed:
            raise InterfaceError("Connection is closed")


class _EmbeddedCursor:
    def __init__(self, connection: _EmbeddedConnection):
        self.connection = connection
        self.arraysize = 1
        self.description = None
        self.rowcount = -1
        self._result_iter = None
        self._closed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def __iter__(self):
        return self

    def __next__(self):
        row = self.fetchone()
        if row is None:
            raise StopIteration
        return row

    def close(self):
        self._closed = True
        self._result_iter = None

    def execute(self, operation: str, params: Optional[Any] = None):
        if self._closed:
            raise InterfaceError("Cursor is closed")
        if self.connection._closed:
            raise InterfaceError("Connection is closed")
        try:
            if params is None:
                result = self.connection._sql.exec(operation)
            else:
                prepared = self.connection._sql.prepare(operation)
                result = self._execute_prepared(prepared, params)
        except Exception as exc:
            raise OperationalError(str(exc)) from exc

        self.description = getattr(result, "description", None)
        self.rowcount = getattr(result, "rowcount", -1)
        self._result_iter = iter(result)
        return self

    def fetchone(self):
        if self._result_iter is None:
            return None
        try:
            return next(self._result_iter)
        except StopIteration:
            return None

    def fetchmany(self, size: Optional[int] = None):
        if size is None:
            size = self.arraysize
        rows = []
        for _ in range(size):
            row = self.fetchone()
            if row is None:
                break
            rows.append(row)
        return rows

    def fetchall(self):
        rows = []
        while True:
            row = self.fetchone()
            if row is None:
                break
            rows.append(row)
        return rows

    @staticmethod
    def _execute_prepared(prepared: Any, params: Any):
        if isinstance(params, dict):
            return prepared.execute(**params)
        if isinstance(params, (str, bytes)):
            return prepared.execute(params)
        if isinstance(params, Iterable):
            return prepared.execute(*params)
        return prepared.execute(params)


class _DBAPI:
    def __init__(self, runtime_manager: Any, sql_getter: Any):
        self._runtime_manager = runtime_manager
        self._sql_getter = sql_getter

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

    def connect(self, *args, mode: str = "auto", **kwargs):
        # Explicit native mode or explicit remote arguments should use native dbapi.
        has_remote_args = bool(args) or any(
            key in kwargs
            for key in (
                "hostname",
                "port",
                "namespace",
                "username",
                "password",
                "connectionstr",
                "accessToken",
            )
        )

        if mode not in ("auto", "embedded", "native"):
            raise InterfaceError(f"Unsupported dbapi mode: {mode}")

        if mode == "native" or (mode == "auto" and has_remote_args):
            return self._connect_native(*args, **kwargs)

        if mode == "embedded":
            return _EmbeddedConnection(self._sql_getter())

        # auto mode without explicit remote arguments: prefer embedded if available.
        runtime_state = self._runtime_manager.get()
        if runtime_state.embedded_available:
            return _EmbeddedConnection(self._sql_getter())

        return self._connect_native(*args, **kwargs)

    def _connect_native(self, *args, **kwargs):
        try:
            native_dbapi = importlib.import_module("iris.dbapi")
        except ImportError as exc:
            raise InterfaceError(
                "Official native DB-API driver is unavailable (expected module: iris.dbapi)"
            ) from exc

        if not hasattr(native_dbapi, "connect"):
            raise InterfaceError("Official native DB-API driver is invalid: missing connect()")

        return native_dbapi.connect(*args, **kwargs)


def make_dbapi(runtime_manager: Any, sql_getter: Any) -> _DBAPI:
    return _DBAPI(runtime_manager=runtime_manager, sql_getter=sql_getter)
