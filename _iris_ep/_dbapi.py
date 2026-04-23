from __future__ import annotations

from collections.abc import Iterable
import importlib
import sys
from typing import Any, Optional


apilevel = "2.0"
threadsafety = 1
paramstyle = "qmark"

_VALID_ISOLATION_LEVELS = frozenset({
    "READ UNCOMMITTED",
    "READ COMMITTED",
    "REPEATABLE READ",
    "SERIALIZABLE",
})

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


_SQL_EMPTY_STRING_SENTINEL = "\x00"


def _normalize_embedded_result_value(value: Any):
    # Embedded %SQL.Statement crosses the SQL/ObjectScript boundary, where
    # SQL NULL becomes the ObjectScript null string ("") and SQL empty string
    # becomes $CHAR(0). Normalize back to Python-facing values here.
    if value == "":
        return None
    if value == _SQL_EMPTY_STRING_SENTINEL:
        return ""
    return value


def _normalize_embedded_result_row(row: Any):
    if isinstance(row, tuple):
        return tuple(_normalize_embedded_result_value(value) for value in row)
    if isinstance(row, list):
        return [_normalize_embedded_result_value(value) for value in row]
    return _normalize_embedded_result_value(row)


def _normalize_embedded_param_value(value: Any):
    # In the embedded SQL/ObjectScript boundary, Python empty string should be
    # sent as the SQL empty-string sentinel so it round-trips distinctly from NULL.
    if value == "":
        return _SQL_EMPTY_STRING_SENTINEL
    return value


def _normalize_embedded_params(params: Any):
    if isinstance(params, dict):
        return {key: _normalize_embedded_param_value(value) for key, value in params.items()}
    if isinstance(params, tuple):
        return tuple(_normalize_embedded_param_value(value) for value in params)
    if isinstance(params, list):
        return [_normalize_embedded_param_value(value) for value in params]
    if isinstance(params, (str, bytes)):
        return _normalize_embedded_param_value(params)
    if isinstance(params, Iterable):
        return [_normalize_embedded_param_value(value) for value in params]
    return _normalize_embedded_param_value(params)


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
        # Pre-built index tuple — avoids constructing range() on every __next__ call.
        self._column_indices: Optional[tuple[int, ...]] = (
            tuple(range(1, column_count + 1))
            if isinstance(column_count, int) and column_count > 0
            else None
        )
        # NOTE: Do NOT pre-bind _Next / _GetData via getattr() here.
        # The IRIS Python bridge uses a single "current method" slot per object;
        # calling getattr(obj, '_GetData') overwrites it and makes any previously
        # returned _Next bound-method raise "Method not found". Always access
        # methods via fresh attribute lookup on self._statement_result.

    def _read_named_cell(self, name: str):
        for candidate in (name, name.upper(), name.lower()):
            try:
                return _normalize_embedded_result_value(getattr(self._statement_result, candidate))
            except Exception:
                continue
        raise InterfaceError("Unsupported %SQL.Statement result object")

    def _read_cell(self, index: int):
        # %GetData(n) is the documented positional accessor for Dynamic SQL.
        getter = getattr(self._statement_result, "_GetData", None)
        if not callable(getter):
            raise InterfaceError("Unsupported %SQL.Statement result object")

        try:
            return _normalize_embedded_result_value(getter(index))
        except Exception as first_exc:
            # Some embedded bridges may map indexes as strings.
            try:
                return _normalize_embedded_result_value(getter(str(index)))
            except Exception as second_exc:
                if "Method not found" in str(first_exc) or "Method not found" in str(second_exc):
                    raise InterfaceError("Unsupported %SQL.Statement result object") from second_exc
                raise

    def __iter__(self):
        return self

    def __next__(self):
        sr = self._statement_result
        if not sr._Next():
            raise StopIteration

        # Fast path: known column count — skip named/slow-path overhead.
        if self._column_indices is not None:
            normalize = _normalize_embedded_result_value
            return tuple(normalize(sr._GetData(i)) for i in self._column_indices)

        if self._projected_columns:
            try:
                return tuple(self._read_named_cell(name) for name in self._projected_columns)
            except Exception:
                pass

        # Fallback: slow path for unusual result objects.
        try:
            return (self._read_cell(1),)
        except Exception as exc:
            raise InterfaceError("Unsupported %SQL.Statement result object") from exc


class _EmbeddedConnection:
    def __init__(
        self,
        cls_getter: Any = None,
        use_statement: bool = False,
        isolation_level: Optional[str] = None,
    ):
        self._cls_getter = cls_getter
        self._use_statement = use_statement
        self._closed = False
        self._cls_fn: Any = None  # cached result of cls_getter() — avoids importlib overhead per execute
        self._sql_statement_class: Any = None  # cached %SQL.Statement class — avoids iris.cls() overhead per execute
        # isolation_level=None means autocommit. Any other value starts a
        # transaction (iris.tstart) before the first DML and requires an
        # explicit commit() or rollback().
        self._isolation_level: Optional[str] = None
        if isolation_level is not None:
            self.isolation_level = isolation_level  # validate via setter

    # ------------------------------------------------------------------
    # PEP 249 transaction attributes
    # ------------------------------------------------------------------

    @property
    def isolation_level(self) -> Optional[str]:
        """Current isolation level, or None for autocommit mode."""
        return self._isolation_level

    @isolation_level.setter
    def isolation_level(self, value: Optional[str]) -> None:
        if value is not None and value.upper() not in _VALID_ISOLATION_LEVELS:
            raise InterfaceError(
                f"Unsupported isolation level: {value!r}. "
                f"Valid levels: {sorted(_VALID_ISOLATION_LEVELS)}"
            )
        self._isolation_level = value.upper() if value is not None else None

    @property
    def autocommit(self) -> bool:
        """True when isolation_level is None (autocommit mode)."""
        return self._isolation_level is None

    @autocommit.setter
    def autocommit(self, value: bool) -> None:
        if value:
            self._isolation_level = None
        elif self._isolation_level is None:
            self._isolation_level = "READ COMMITTED"

    def _ensure_transaction(self) -> None:
        """Start a transaction if not in autocommit mode and none is active."""
        if self._isolation_level is None:
            return  # autocommit — nothing to do
        import iris as _iris
        if _iris.tlevel() == 0:
            # Set isolation level before opening the transaction.
            self._exec_sql(f"SET TRANSACTION ISOLATION LEVEL {self._isolation_level}")
            _iris.tstart()

    def _exec_sql(self, sql: str) -> None:
        """Execute a single SQL statement with no result (DDL / SET)."""
        if self._cls_fn is None:
            return  # not yet initialised — skip (e.g. called before first execute)
        if self._sql_statement_class is None:
            self._sql_statement_class = self._cls_fn("%SQL.Statement")
        stmt = self._sql_statement_class._New()
        stmt._Prepare(sql)
        stmt._Execute()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type is not None:
            self.rollback()
        else:
            self.commit()
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
        try:
            import iris as _iris
            if _iris.tlevel() > 0:
                _iris.tcommit()
        except Exception as exc:
            raise OperationalError(str(exc)) from exc

    def rollback(self):
        if self._closed:
            raise InterfaceError("Connection is closed")
        try:
            import iris as _iris
            if _iris.tlevel() > 0:
                _iris.trollback()  # roll back ALL nesting levels
        except Exception as exc:
            raise OperationalError(str(exc)) from exc


class _EmbeddedCursor:
    def __init__(self, connection: _EmbeddedConnection):
        self.connection = connection
        self.arraysize = 1
        self.description = None
        self.rowcount = -1
        self._result_iter = None
        self._closed = False
        # Caches keyed by SQL string — avoids _New()/_Prepare(), projection parsing,
        # and _ResultColumnCount probing on repeated execute() calls.
        self._statement_cache: dict[str, Any] = {}
        self._projection_cache: dict[str, Optional[list[str]]] = {}
        self._column_count_cache: dict[str, int] = {}

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
        self._statement_cache.clear()
        self._projection_cache.clear()
        self._column_count_cache.clear()

    def execute(self, operation: str, params: Optional[Any] = None):
        if self._closed:
            raise InterfaceError("Cursor is closed")
        if self.connection._closed:
            raise InterfaceError("Connection is closed")
        # Discard previous result BEFORE executing new statement.
        # Deferring GC of the old %SQL.StatementResult until AFTER _Execute()
        # can corrupt the new result (IRIS %OnClose side-effects on shared state).
        self._result_iter = None
        try:
            self.connection._ensure_transaction()
            result = self._execute_with_statement(operation, params)

            if operation not in self._projection_cache:
                self._projection_cache[operation] = self._parse_select_projection(operation)
            projected_columns = self._projection_cache[operation]

            known_col_count = self._column_count_cache.get(operation)
            result_iter = self._make_statement_result_iter(result, projected_columns, known_col_count)
            if result_iter is None:
                raise InterfaceError("Unsupported %SQL.Statement result object")

            # Persist column count from projected_columns on first execution.
            if known_col_count is None and isinstance(result_iter, _StatementResultIterator):
                if result_iter._column_count is not None:
                    self._column_count_cache[operation] = result_iter._column_count

            self.description = None
            self.rowcount = -1
            self._result_iter = result_iter
        except Error:
            raise
        except Exception as exc:
            raise OperationalError(str(exc)) from exc

        return self

    def executemany(self, operation: str, seq_of_parameters: Any):
        """Execute an operation against a sequence of parameter sets."""
        if self._closed:
            raise InterfaceError("Cursor is closed")
        if self.connection._closed:
            raise InterfaceError("Connection is closed")
        self._result_iter = None
        try:
            self.connection._ensure_transaction()
            for params in seq_of_parameters:
                self._execute_with_statement(operation, params)
            self.description = None
            self.rowcount = -1
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

        # Cache cls_fn on the connection: cls_getter() triggers RuntimeManager.get()
        # -> refresh() -> can_import_embedded_python() -> importlib.import_module each call.
        if self.connection._cls_fn is None:
            cls_fn = cls_getter()
            if not callable(cls_fn):
                raise InterfaceError("Embedded %SQL.Statement API is unavailable")
            self.connection._cls_fn = cls_fn
        cls_fn = self.connection._cls_fn

        try:
            if operation in self._statement_cache:
                statement = self._statement_cache[operation]
            else:
                if self.connection._sql_statement_class is None:
                    self.connection._sql_statement_class = cls_fn("%SQL.Statement")
                statement = self.connection._sql_statement_class._New()
                statement._Prepare(operation)
                self._statement_cache[operation] = statement
            normalized_params = _normalize_embedded_params(params)

            if params is None:
                raw = statement._Execute()
            elif isinstance(normalized_params, dict):
                raw = statement._Execute(**normalized_params)
            elif isinstance(normalized_params, (str, bytes)):
                raw = statement._Execute(normalized_params)
            elif isinstance(normalized_params, Iterable):
                raw = statement._Execute(*normalized_params)
            else:
                raw = statement._Execute(normalized_params)

            return raw
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
            else:
                # Bare column name (possibly table-qualified): strip qualifier and quotes.
                bare = item.split(".")[-1].strip().strip('"[]`')
                if bare and bare != "*":
                    columns.append(bare)

        return columns or None

    @staticmethod
    def _make_statement_result_iter(
        result: Any,
        projected_columns: Optional[list[str]] = None,
        known_col_count: Optional[int] = None,
    ):
        try:
            # Fast path: column count already known — skip all probing.
            if known_col_count is not None and known_col_count > 0:
                return _StatementResultIterator(
                    result,
                    column_count=known_col_count,
                    projected_columns=projected_columns,
                )

            # Derive column count from projected columns when available — avoids
            # any property/method access on the result object before iteration
            # starts.
            column_count: Optional[int] = None
            if projected_columns:
                column_count = len(projected_columns)

            return _StatementResultIterator(
                result,
                column_count=column_count,
                projected_columns=projected_columns,
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

    def connect(self, *args, mode: str = "auto", isolation_level: Optional[str] = None, **kwargs):
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
            return _EmbeddedConnection(self._cls_getter, use_statement=True, isolation_level=isolation_level)

        raise InterfaceError(f"Unsupported dbapi mode: {mode}")

    def _connect_native(self, *args, **kwargs):
        try:
            native_dbapi = importlib.import_module("iris.dbapi")
        except ImportError as exc:
            raise InterfaceError(
                "Official native DB-API driver is unavailable (expected module: iris.dbapi)"
            ) from exc

        self._restore_public_facade(native_dbapi)

        if not hasattr(native_dbapi, "connect"):
            raise InterfaceError("Official native DB-API driver is invalid: missing connect()")

        return native_dbapi.connect(*args, **kwargs)

    def _restore_public_facade(self, native_dbapi: Any):
        parent_module = sys.modules.get("iris")
        if parent_module is None:
            return

        try:
            current_dbapi = getattr(parent_module, "dbapi", None)
        except Exception:
            return

        if current_dbapi is native_dbapi:
            try:
                setattr(parent_module, "dbapi", self)
            except Exception:
                pass


def make_dbapi(runtime_manager: Any, cls_getter: Any = None) -> _DBAPI:
    return _DBAPI(runtime_manager=runtime_manager, cls_getter=cls_getter)
