import iris_embedded_python as iris
import _iris_ep
import _iris_ep._dbapi as embedded_dbapi
import _iris_ep._dbapi_native as native_dbapi_loader
import pytest
import sys
import types


class FakeStatementResult:
    def __init__(self, rows):
        self._rows = rows
        self._index = -1
        self._column_count = len(rows[0]) if rows else 0

    def _Next(self):
        self._index += 1
        return self._index < len(self._rows)

    def _GetData(self, index):
        return self._rows[self._index][index - 1]

    def _Get(self, index):
        return self._GetData(index)

    def _GetColumnCount(self):
        return self._column_count


class FakeStatementResultNoColumnCount:
    def __init__(self, rows):
        self._rows = rows
        self._index = -1

    def _Next(self):
        self._index += 1
        return self._index < len(self._rows)

    def _GetData(self, index):
        row = self._rows[self._index]
        if index < 1 or index > len(row):
            raise IndexError(index)
        return row[index - 1]

    def _Get(self, index):
        return self._GetData(index)


class FakeStatementResultNoColumnCountInfinite:
    def __init__(self):
        self._seen = 0

    def _Next(self):
        # Single row shape for test purposes.
        self._seen += 1
        return self._seen == 1

    def _GetData(self, index):
        # Never raises, which previously caused an infinite loop.
        return index

    def _Get(self, index):
        return self._GetData(index)


class FakeStatementResultGetDataOnly:
    def __init__(self, rows):
        self._rows = rows
        self._index = -1
        self._column_count = len(rows[0]) if rows else 0

    def _Next(self):
        self._index += 1
        return self._index < len(self._rows)

    def _GetData(self, index):
        return self._rows[self._index][index - 1]

    def _GetColumnCount(self):
        return self._column_count


class FakeStatementResultAttrOnly:
    def __init__(self, rows, columns):
        self._rows = rows
        self._columns = columns
        self._index = -1

    def _Next(self):
        self._index += 1
        if self._index >= len(self._rows):
            return False

        row = self._rows[self._index]
        for name, value in zip(self._columns, row):
            setattr(self, name, value)
            setattr(self, name.upper(), value)
        return True


class FakeStatement:
    def __init__(self, rows):
        self.rows = rows
        self.prepare_seen = None
        self.execute_args = None
        self.execute_kwargs = None

    def _Prepare(self, query):
        self.prepare_seen = query
        return 1

    def _Execute(self, *args, **kwargs):
        self.execute_args = args
        self.execute_kwargs = kwargs
        return FakeStatementResult(self.rows)


class FakeStatementNoColumnCount(FakeStatement):
    def _Execute(self, *args, **kwargs):
        self.execute_args = args
        self.execute_kwargs = kwargs
        return FakeStatementResultNoColumnCount(self.rows)


class FakeStatementNoColumnCountInfinite(FakeStatement):
    def _Execute(self, *args, **kwargs):
        self.execute_args = args
        self.execute_kwargs = kwargs
        return FakeStatementResultNoColumnCountInfinite()


class FakeStatementGetDataOnly(FakeStatement):
    def _Execute(self, *args, **kwargs):
        self.execute_args = args
        self.execute_kwargs = kwargs
        return FakeStatementResultGetDataOnly(self.rows)


class FakeStatementAttrOnly(FakeStatement):
    def __init__(self, rows, columns):
        super().__init__(rows)
        self.columns = columns

    def _Execute(self, *args, **kwargs):
        self.execute_args = args
        self.execute_kwargs = kwargs
        return FakeStatementResultAttrOnly(self.rows, self.columns)


class FakeStatementFactory:
    def __init__(self, statement):
        self.statement = statement

    def _New(self):
        return self.statement


class FakeNamespaceProcess:
    def __init__(self, namespace="BASE"):
        self.namespace = namespace
        self.calls = []

    def NameSpace(self):
        self.calls.append(("NameSpace", self.namespace))
        return self.namespace

    def SetNamespace(self, namespace):
        self.calls.append(("SetNamespace", namespace))
        self.namespace = namespace
        return namespace


class FakeNamespaceStatementResult:
    def __init__(self, process):
        self.process = process
        self._seen = False

    def _Next(self):
        if self._seen:
            return False
        self._seen = True
        return True

    def _GetData(self, index):
        assert index == 1
        return self.process.namespace


class FakeNamespaceStatement:
    def __init__(self, process):
        self.process = process
        self.prepare_seen = None
        self.execute_namespaces = []

    def _Prepare(self, query):
        self.prepare_seen = query
        return 1

    def _Execute(self, *args, **kwargs):
        self.execute_namespaces.append(self.process.namespace)
        return FakeNamespaceStatementResult(self.process)


class FakeNamespaceStatementFactory:
    def __init__(self, process):
        self.process = process
        self.statements = []

    def _New(self):
        statement = FakeNamespaceStatement(self.process)
        self.statements.append(statement)
        return statement


def test_dbapi_embedded_execute_and_fetch(monkeypatch):
    fake_statement = FakeStatement([(10, "x"), (20, "y")])

    def fake_cls(name):
        assert name == "%SQL.Statement"
        return FakeStatementFactory(fake_statement)

    monkeypatch.setattr(_iris_ep, "cls", fake_cls, raising=False)
    monkeypatch.setattr(
        _iris_ep.dbapi._runtime_manager,
        "get",
        lambda: types.SimpleNamespace(
            embedded_available=True,
            state="embedded-kernel",
            dbapi=None,
        ),
    )

    conn = iris.dbapi.connect(mode="embedded")
    cur = conn.cursor()

    cur.execute("select * from Demo")
    assert fake_statement.prepare_seen == "select * from Demo"
    assert cur.description == (
        ("1", None, None, None, None, None, None),
        ("2", None, None, None, None, None, None),
    )
    assert cur.rowcount == -1
    assert cur.fetchone() == (10, "x")
    assert cur.fetchmany(1) == [(20, "y")]
    assert cur.fetchall() == []

    cur.close()
    conn.close()


def test_dbapi_embedded_normalizes_sql_null_and_empty_string(monkeypatch):
    fake_statement = FakeStatement([("", "\x00", "plain", None)])

    def fake_cls(name):
        assert name == "%SQL.Statement"
        return FakeStatementFactory(fake_statement)

    monkeypatch.setattr(_iris_ep, "cls", fake_cls, raising=False)
    monkeypatch.setattr(
        _iris_ep.dbapi._runtime_manager,
        "get",
        lambda: types.SimpleNamespace(
            embedded_available=True,
            state="embedded-kernel",
            dbapi=None,
        ),
    )

    conn = iris.dbapi.connect(mode="embedded")
    cur = conn.cursor()
    cur.execute("select 1")

    assert cur.fetchone() == (None, "", "plain", None)


def test_dbapi_embedded_prepared_params(monkeypatch):
    fake_statement = FakeStatement([(1, "a")])

    def fake_cls(name):
        assert name == "%SQL.Statement"
        return FakeStatementFactory(fake_statement)

    monkeypatch.setattr(_iris_ep, "cls", fake_cls, raising=False)
    monkeypatch.setattr(
        _iris_ep.dbapi._runtime_manager,
        "get",
        lambda: types.SimpleNamespace(
            embedded_available=True,
            state="embedded-kernel",
            dbapi=None,
        ),
    )

    conn = iris.dbapi.connect(mode="embedded")
    cur = conn.cursor()

    cur.execute("select * from Demo where id=? and name=?", (7, "z"))

    assert fake_statement.prepare_seen == "select * from Demo where id=? and name=?"
    assert fake_statement.execute_args == (7, "z")
    assert fake_statement.execute_kwargs == {}


def test_dbapi_embedded_prepared_params_normalize_empty_string(monkeypatch):
    fake_statement = FakeStatement([(1, "a")])

    def fake_cls(name):
        assert name == "%SQL.Statement"
        return FakeStatementFactory(fake_statement)

    monkeypatch.setattr(_iris_ep, "cls", fake_cls, raising=False)
    monkeypatch.setattr(
        _iris_ep.dbapi._runtime_manager,
        "get",
        lambda: types.SimpleNamespace(
            embedded_available=True,
            state="embedded-kernel",
            dbapi=None,
        ),
    )

    conn = iris.dbapi.connect(mode="embedded")
    cur = conn.cursor()

    cur.execute("select * from Demo where a=? and b=? and c=?", ("", None, "z"))

    assert fake_statement.execute_args == ("\x00", "", "z")


def test_dbapi_embedded_prepared_dict_params_normalize_empty_string(monkeypatch):
    fake_statement = FakeStatement([(1, "a")])

    def fake_cls(name):
        assert name == "%SQL.Statement"
        return FakeStatementFactory(fake_statement)

    monkeypatch.setattr(_iris_ep, "cls", fake_cls, raising=False)
    monkeypatch.setattr(
        _iris_ep.dbapi._runtime_manager,
        "get",
        lambda: types.SimpleNamespace(
            embedded_available=True,
            state="embedded-kernel",
            dbapi=None,
        ),
    )

    conn = iris.dbapi.connect(mode="embedded")
    cur = conn.cursor()

    cur.execute("select * from Demo where a=:a and b=:b", {"a": "", "b": None})

    assert fake_statement.execute_kwargs == {"a": "\x00", "b": ""}


def test_dbapi_embedded_prefers_sql_statement(monkeypatch):
    fake_statement = FakeStatement([(3, "c"), (4, "d")])

    def fake_cls(name):
        assert name == "%SQL.Statement"
        return FakeStatementFactory(fake_statement)

    monkeypatch.setattr(_iris_ep, "cls", fake_cls, raising=False)
    monkeypatch.setattr(
        _iris_ep.dbapi._runtime_manager,
        "get",
        lambda: types.SimpleNamespace(
            embedded_available=True,
            state="embedded-kernel",
            dbapi=None,
        ),
    )

    conn = iris.dbapi.connect(mode="embedded")
    cur = conn.cursor()
    cur.execute("select * from Demo where id=?", (3,))

    # %SQL.Statement path should be used first.
    assert fake_statement.prepare_seen == "select * from Demo where id=?"
    assert fake_statement.execute_args == (3,)
    assert fake_statement.execute_kwargs == {}
    assert cur.fetchall() == [(3, "c"), (4, "d")]


def test_dbapi_embedded_result_without_column_count(monkeypatch):
    fake_statement = FakeStatementNoColumnCount([(42,)])

    def fake_cls(name):
        assert name == "%SQL.Statement"
        return FakeStatementFactory(fake_statement)

    monkeypatch.setattr(_iris_ep, "cls", fake_cls, raising=False)
    monkeypatch.setattr(
        _iris_ep.dbapi._runtime_manager,
        "get",
        lambda: types.SimpleNamespace(
            mode="auto",
            embedded_available=True,
            state="embedded-local",
            dbapi=None,
        ),
    )

    conn = iris.dbapi.connect()
    cur = conn.cursor()
    cur.execute("select 1")

    assert cur.fetchone() == (42,)


def test_dbapi_embedded_result_without_column_count_does_not_hang(monkeypatch):
    fake_statement = FakeStatementNoColumnCountInfinite([])

    def fake_cls(name):
        assert name == "%SQL.Statement"
        return FakeStatementFactory(fake_statement)

    monkeypatch.setattr(_iris_ep, "cls", fake_cls, raising=False)
    monkeypatch.setattr(
        _iris_ep.dbapi._runtime_manager,
        "get",
        lambda: types.SimpleNamespace(
            mode="auto",
            embedded_available=True,
            state="embedded-local",
            dbapi=None,
        ),
    )

    conn = iris.dbapi.connect()
    cur = conn.cursor()
    cur.execute("select 1")

    assert cur.fetchone() == (1,)


def test_dbapi_embedded_falls_back_to_getdata_accessor(monkeypatch):
    fake_statement = FakeStatementGetDataOnly([(7, "gd")])

    def fake_cls(name):
        assert name == "%SQL.Statement"
        return FakeStatementFactory(fake_statement)

    monkeypatch.setattr(_iris_ep, "cls", fake_cls, raising=False)
    monkeypatch.setattr(
        _iris_ep.dbapi._runtime_manager,
        "get",
        lambda: types.SimpleNamespace(
            mode="auto",
            embedded_available=True,
            state="embedded-local",
            dbapi=None,
        ),
    )

    conn = iris.dbapi.connect()
    cur = conn.cursor()
    cur.execute("select 1")

    assert cur.fetchone() == (7, "gd")


def test_dbapi_embedded_falls_back_to_projection_attributes(monkeypatch):
    fake_statement = FakeStatementAttrOnly([(9,)], ["result"])

    def fake_cls(name):
        assert name == "%SQL.Statement"
        return FakeStatementFactory(fake_statement)

    monkeypatch.setattr(_iris_ep, "cls", fake_cls, raising=False)
    monkeypatch.setattr(
        _iris_ep.dbapi._runtime_manager,
        "get",
        lambda: types.SimpleNamespace(
            mode="auto",
            embedded_available=True,
            state="embedded-local",
            dbapi=None,
        ),
    )

    conn = iris.dbapi.connect()
    cur = conn.cursor()
    cur.execute("SELECT 1 AS result")

    assert cur.fetchone() == (9,)


def test_dbapi_embedded_mode_accepts_embedded_local(monkeypatch):
    fake_statement = FakeStatement([(11, "local")])

    def fake_cls(name):
        assert name == "%SQL.Statement"
        return FakeStatementFactory(fake_statement)

    monkeypatch.setattr(_iris_ep, "cls", fake_cls, raising=False)
    monkeypatch.setattr(
        _iris_ep.dbapi._runtime_manager,
        "get",
        lambda: types.SimpleNamespace(
            embedded_available=True,
            state="embedded-local",
            dbapi=None,
        ),
    )

    conn = iris.dbapi.connect(mode="embedded")
    cur = conn.cursor()
    cur.execute("select 1")

    assert fake_statement.prepare_seen == "select 1"
    assert cur.fetchone() == (11, "local")


def test_dbapi_auto_mode_defaults_to_embedded(monkeypatch):
    fake_statement = FakeStatement([(5, "e")])

    def fake_cls(name):
        assert name == "%SQL.Statement"
        return FakeStatementFactory(fake_statement)

    monkeypatch.setattr(_iris_ep, "cls", fake_cls, raising=False)
    monkeypatch.setattr(
        _iris_ep.dbapi._runtime_manager,
        "get",
        lambda: types.SimpleNamespace(
            mode="auto",
            embedded_available=True,
            state="embedded-kernel",
            dbapi=None,
        ),
    )

    conn = iris.dbapi.connect()
    cur = conn.cursor()
    cur.execute("select 1")

    assert fake_statement.prepare_seen == "select 1"
    assert cur.fetchone() == (5, "e")


def test_dbapi_auto_mode_accepts_embedded_local(monkeypatch):
    fake_statement = FakeStatement([(6, "local")])

    def fake_cls(name):
        assert name == "%SQL.Statement"
        return FakeStatementFactory(fake_statement)

    monkeypatch.setattr(_iris_ep, "cls", fake_cls, raising=False)
    monkeypatch.setattr(
        _iris_ep.dbapi._runtime_manager,
        "get",
        lambda: types.SimpleNamespace(
            mode="auto",
            embedded_available=True,
            state="embedded-local",
            dbapi=None,
        ),
    )

    conn = iris.dbapi.connect()
    cur = conn.cursor()
    cur.execute("select 1")

    assert fake_statement.prepare_seen == "select 1"
    assert cur.fetchone() == (6, "local")


def test_dbapi_auto_mode_uses_bound_runtime_dbapi_in_native_mode(monkeypatch):
    bound_conn = object()

    monkeypatch.setattr(
        _iris_ep.dbapi._runtime_manager,
        "get",
        lambda: types.SimpleNamespace(
            mode="native",
            embedded_available=True,
            state="embedded-local",
            dbapi=bound_conn,
        ),
    )

    assert iris.dbapi.connect() is bound_conn


def test_dbapi_auto_mode_rejects_native_runtime_without_bound_dbapi(monkeypatch):
    monkeypatch.setattr(
        _iris_ep.dbapi._runtime_manager,
        "get",
        lambda: types.SimpleNamespace(
            mode="native",
            embedded_available=True,
            state="embedded-local",
            dbapi=None,
        ),
    )

    with pytest.raises(iris.dbapi.InterfaceError, match="cannot infer a native DB-API connection"):
        iris.dbapi.connect()


def test_dbapi_auto_mode_rejects_unavailable_runtime(monkeypatch):
    monkeypatch.setattr(
        _iris_ep.dbapi._runtime_manager,
        "get",
        lambda: types.SimpleNamespace(mode="auto", embedded_available=False, state="unavailable", dbapi=None),
    )

    with pytest.raises(iris.dbapi.InterfaceError, match="embedded"):
        iris.dbapi.connect()


def test_dbapi_connect_remains_independent_from_runtime_binding(monkeypatch):
    fake_statement = FakeStatement([(1, "a")])

    def fake_cls(name):
        assert name == "%SQL.Statement"
        return FakeStatementFactory(fake_statement)

    monkeypatch.setattr(_iris_ep, "cls", fake_cls, raising=False)
    monkeypatch.setattr(
        _iris_ep.dbapi._runtime_manager,
        "get",
        lambda: types.SimpleNamespace(
            embedded_available=True,
            state="embedded-kernel",
            dbapi=None,
        ),
    )

    iris.runtime.reset()
    assert iris.runtime.dbapi is None

    conn = iris.dbapi.connect(mode="embedded")

    assert conn is not None
    assert iris.runtime.dbapi is None

    iris.runtime.reset()


def test_dbapi_embedded_namespace_switches_per_logical_connection(monkeypatch):
    process = FakeNamespaceProcess(namespace="BASE")
    statement_factory = FakeNamespaceStatementFactory(process)

    def fake_cls(name):
        assert name == "%SQL.Statement"
        return statement_factory

    monkeypatch.setattr(_iris_ep, "cls", fake_cls, raising=False)
    monkeypatch.setattr(
        _iris_ep.dbapi._runtime_manager,
        "get",
        lambda: types.SimpleNamespace(
            embedded_available=True,
            state="embedded-kernel",
            dbapi=None,
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "iris",
        types.SimpleNamespace(system=types.SimpleNamespace(Process=process)),
    )

    conn_user = iris.dbapi.connect(mode="embedded", namespace="USER")
    conn_samples = iris.dbapi.connect(mode="embedded", namespace="SAMPLES")

    cur_user = conn_user.cursor()
    cur_samples = conn_samples.cursor()

    cur_user.execute("SELECT 1 AS result")
    cur_samples.execute("SELECT 1 AS result")

    assert statement_factory.statements[0].execute_namespaces == ["USER"]
    assert statement_factory.statements[1].execute_namespaces == ["SAMPLES"]
    assert cur_user.fetchone() == ("USER",)
    assert cur_samples.fetchone() == ("SAMPLES",)
    assert process.namespace == "BASE"


def test_dbapi_auto_mode_rejects_namespace_only_ambiguity(monkeypatch):
    monkeypatch.setattr(
        _iris_ep.dbapi._runtime_manager,
        "get",
        lambda: types.SimpleNamespace(
            mode="auto",
            embedded_available=True,
            state="embedded-kernel",
            dbapi=None,
        ),
    )

    with pytest.raises(iris.dbapi.InterfaceError, match="cannot infer whether namespace"):
        iris.dbapi.connect(namespace="USER")


def test_dbapi_native_uses_official_iris_dbapi(monkeypatch):
    calls = []

    class FakeNativeDBAPI:
        @staticmethod
        def connect(*args, **kwargs):
            return {"args": args, "kwargs": kwargs}

    def fake_import_module(name):
        calls.append(name)
        if name == "iris.dbapi":
            return FakeNativeDBAPI
        raise ImportError(name)

    monkeypatch.setattr(native_dbapi_loader.importlib, "import_module", fake_import_module)

    conn = iris.dbapi.connect(mode="native", hostname="localhost", port=1972)

    assert calls == ["iris.dbapi"]
    assert conn["kwargs"]["hostname"] == "localhost"
    assert conn["kwargs"]["port"] == 1972


def test_dbapi_native_import_preserves_public_facade(monkeypatch):
    calls = []
    facade = iris.dbapi
    parent_module = types.ModuleType("iris")
    parent_module.dbapi = facade

    class FakeNativeDBAPI:
        @staticmethod
        def connect(*args, **kwargs):
            return {"args": args, "kwargs": kwargs}

    def fake_import_module(name):
        calls.append(name)
        if name == "iris.dbapi":
            parent_module.dbapi = FakeNativeDBAPI
            return FakeNativeDBAPI
        raise ImportError(name)

    monkeypatch.setitem(sys.modules, "iris", parent_module)
    monkeypatch.setattr(native_dbapi_loader.importlib, "import_module", fake_import_module)

    conn = facade.connect(mode="native", hostname="localhost", port=1972)

    assert calls == ["iris.dbapi"]
    assert conn["kwargs"]["hostname"] == "localhost"
    assert parent_module.dbapi is facade


def test_dbapi_native_import_falls_back_to_installed_distribution(monkeypatch, tmp_path):
    package_dir = tmp_path / "iris"
    dbapi_dir = package_dir / "dbapi"
    dbapi_dir.mkdir(parents=True)
    (package_dir / "__init__.py").write_text('origin = "official"\n')
    (dbapi_dir / "__init__.py").write_text(
        "import iris\n\n"
        "def connect(*args, **kwargs):\n"
        "    return {'origin': iris.origin, 'args': args, 'kwargs': kwargs}\n"
    )

    class FakeDistribution:
        @staticmethod
        def locate_file(path):
            return tmp_path / path

    facade = types.ModuleType("iris")
    facade.dbapi = object()

    monkeypatch.setitem(sys.modules, "iris", facade)
    monkeypatch.delitem(sys.modules, "iris.dbapi", raising=False)
    monkeypatch.setattr(
        native_dbapi_loader.importlib.metadata,
        "distribution",
        lambda name: FakeDistribution(),
    )

    try:
        native_dbapi = embedded_dbapi._DBAPI._import_native_dbapi()
        conn = native_dbapi.connect(hostname="localhost")

        assert conn["origin"] == "official"
        assert conn["kwargs"]["hostname"] == "localhost"
        assert sys.modules["iris"] is facade
    finally:
        sys.modules.pop("iris.dbapi", None)


def test_dbapi_native_errors_when_official_module_missing(monkeypatch):
    def fake_import_module(name):
        raise ImportError(name)

    monkeypatch.setattr(native_dbapi_loader.importlib, "import_module", fake_import_module)
    monkeypatch.setattr(
        native_dbapi_loader.importlib.metadata,
        "distribution",
        lambda name: (_ for _ in ()).throw(
            native_dbapi_loader.importlib.metadata.PackageNotFoundError(name)
        ),
    )

    with pytest.raises(iris.dbapi.InterfaceError, match="iris.dbapi"):
        iris.dbapi.connect(mode="native", hostname="localhost", port=1972)
