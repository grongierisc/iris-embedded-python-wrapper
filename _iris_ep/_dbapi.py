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


class _StatementResultIterator:
    def __init__(
        self,
        statement_result: Any,
        column_count: Optional[int] = None,
        projected_columns: Optional[list[str]] = None,
    ):
        self._statement_result = statement_result
        self._column_count = column_count
        self._projected_columns = projected_columns or []

    def _read_named_cell(self, name: str):
        for candidate in (name, name.upper(), name.lower()):
            try:
                return getattr(self._statement_result, candidate)
            except Exception:
                continue
        raise InterfaceError("Unsupported %SQL.Statement result object")

    def _read_cell(self, index: int):
        # %GetData(n) is the documented positional accessor for Dynamic SQL.
        getter = getattr(self._statement_result, "_GetData", None)
        if not callable(getter):
            raise InterfaceError("Unsupported %SQL.Statement result object")

        try:
            return getter(index)
        except Exception as first_exc:
            # Some embedded bridges may map indexes as strings.
            try:
                return getter(str(index))
            except Exception as second_exc:
                if "Method not found" in str(first_exc) or "Method not found" in str(second_exc):
                    raise InterfaceError("Unsupported %SQL.Statement result object") from second_exc
                raise

    def __iter__(self):
        return self

    def __next__(self):
        if not self._statement_result._Next():
            raise StopIteration
        if isinstance(self._column_count, int) and self._column_count > 0:
            return tuple(self._read_cell(index) for index in range(1, self._column_count + 1))

        if self._projected_columns:
            try:
                return tuple(self._read_named_cell(name) for name in self._projected_columns)
            except Exception:
                pass

        # Some embedded result objects don't expose column-count helpers.
        # Avoid probing out-of-range column indexes because that can crash
        # low-level native code on some runtimes.
        try:
            return (self._read_cell(1),)
        except Exception as exc:
            raise InterfaceError("Unsupported %SQL.Statement result object") from exc


class _EmbeddedConnection:
    def __init__(self, cls_getter: Any = None, use_statement: bool = False):
        self._cls_getter = cls_getter
        self._use_statement = use_statement
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
            result = self._execute_with_statement(operation, params)
            projected_columns = self._parse_select_projection(operation)
            result_iter = self._make_statement_result_iter(result, projected_columns)
            if result_iter is None:
                raise InterfaceError("Unsupported %SQL.Statement result object")

            # Keep conservative defaults for statement path to avoid
            # unsafe attribute probing on low-level embedded objects.
            self.description = None
            self.rowcount = -1
            self._result_iter = result_iter
        except Error:
            raise
        except Exception as exc:
            raise OperationalError(str(exc)) from exc

        return self

    def _execute_with_statement(self, operation: str, params: Optional[Any]):
        if not self.connection._use_statement:
            raise InterfaceError(
                "Embedded DB-API requires embedded runtime (embedded-kernel or embedded-local) with %SQL.Statement"
            )

        cls_getter = self.connection._cls_getter
        if cls_getter is None:
            raise InterfaceError("Embedded %SQL.Statement API is unavailable")
        cls_fn = cls_getter()
        if not callable(cls_fn):
            raise InterfaceError("Embedded %SQL.Statement API is unavailable")

        try:
            statement_class: Any = cls_fn("%SQL.Statement")
            statement = statement_class._New()
            statement._Prepare(operation)

            if params is None:
                return statement._Execute()

            if isinstance(params, dict):
                return statement._Execute(**params)

            if isinstance(params, (str, bytes)):
                return statement._Execute(params)

            if isinstance(params, Iterable):
                return statement._Execute(*params)

            return statement._Execute(params)
        except Exception as exc:
            raise OperationalError(str(exc)) from exc

    @staticmethod
    def _parse_select_projection(operation: str) -> Optional[list[str]]:
        sql = operation.strip()
        sql_lower = sql.lower()
        if not sql_lower.startswith("select"):
            return None

        select_part = sql[6:]
        from_pos = select_part.lower().find(" from ")
        if from_pos != -1:
            select_part = select_part[:from_pos]

        columns = []
        for raw_item in select_part.split(","):
            item = raw_item.strip()
            if not item:
                continue

            lower_item = item.lower()
            if " as " in lower_item:
                alias = item[lower_item.rfind(" as ") + 4 :].strip()
                alias = alias.strip('"[]`')
                if alias:
                    columns.append(alias)

        return columns or None

    @staticmethod
    def _make_statement_result_iter(result: Any, projected_columns: Optional[list[str]] = None):
        try:
            try:
                # Prefer runtime-provided iterator when available.
                return iter(result)
            except Exception:
                pass

            column_count = None
            try:
                candidate = result._ResultColumnCount
                if isinstance(candidate, int) and candidate > 0:
                    column_count = candidate
            except Exception:
                column_count = None

            if column_count is None:
                try:
                    candidate = result._GetColumnCount()
                    if isinstance(candidate, int) and candidate > 0:
                        column_count = candidate
                except Exception:
                    column_count = None

            return iter(
                _StatementResultIterator(
                    result,
                    column_count=column_count,
                    projected_columns=projected_columns,
                )
            )
        except Exception:
            return None

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

        runtime_state = self._runtime_manager.get()

        if mode in ("embedded", "auto"):
            if not runtime_state.embedded_available or runtime_state.state not in (
                "embedded-kernel",
                "embedded-local",
            ):
                raise InterfaceError(
                    "Embedded DB-API is only available in embedded runtime (embedded-kernel or embedded-local) via %SQL.Statement"
                )
            return _EmbeddedConnection(self._cls_getter, use_statement=True)

        raise InterfaceError(f"Unsupported dbapi mode: {mode}")

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


def make_dbapi(runtime_manager: Any, cls_getter: Any = None) -> _DBAPI:
    return _DBAPI(runtime_manager=runtime_manager, cls_getter=cls_getter)
