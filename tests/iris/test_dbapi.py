import iris_embedded_python as iris
import _iris_ep
import _iris_ep._dbapi as embedded_dbapi
import pytest


class FakeResult:
    def __init__(self, rows):
        self._rows = list(rows)
        self.description = [("col1",), ("col2",)]
        self.rowcount = len(self._rows)

    def __iter__(self):
        return iter(self._rows)


class FakePrepared:
    def __init__(self, rows):
        self._rows = rows
        self.args_seen = None
        self.kwargs_seen = None

    def execute(self, *args, **kwargs):
        self.args_seen = args
        self.kwargs_seen = kwargs
        return FakeResult(self._rows)


class FakeSQL:
    def __init__(self):
        self.exec_seen = None
        self.prepared = FakePrepared([(1, "a"), (2, "b")])

    def exec(self, query):
        self.exec_seen = query
        return FakeResult([(10, "x"), (20, "y")])

    def prepare(self, query):
        self.prepared_query = query
        return self.prepared


def test_dbapi_embedded_execute_and_fetch(monkeypatch):
    fake_sql = FakeSQL()
    monkeypatch.setattr(_iris_ep, "sql", fake_sql, raising=False)

    conn = iris.dbapi.connect(mode="embedded")
    cur = conn.cursor()

    cur.execute("select * from Demo")
    assert fake_sql.exec_seen == "select * from Demo"
    assert cur.description == [("col1",), ("col2",)]
    assert cur.rowcount == 2
    assert cur.fetchone() == (10, "x")
    assert cur.fetchmany(1) == [(20, "y")]
    assert cur.fetchall() == []

    cur.close()
    conn.close()


def test_dbapi_embedded_prepared_params(monkeypatch):
    fake_sql = FakeSQL()
    monkeypatch.setattr(_iris_ep, "sql", fake_sql, raising=False)

    conn = iris.dbapi.connect(mode="embedded")
    cur = conn.cursor()

    cur.execute("select * from Demo where id=? and name=?", (7, "z"))

    assert fake_sql.prepared_query == "select * from Demo where id=? and name=?"
    assert fake_sql.prepared.args_seen == (7, "z")
    assert fake_sql.prepared.kwargs_seen == {}


def test_dbapi_connect_remains_independent_from_runtime_binding(monkeypatch):
    fake_sql = FakeSQL()
    monkeypatch.setattr(_iris_ep, "sql", fake_sql, raising=False)

    iris.runtime.reset()
    assert iris.runtime.dbapi is None

    conn = iris.dbapi.connect(mode="embedded")

    assert conn is not None
    assert iris.runtime.dbapi is None

    iris.runtime.reset()


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

    monkeypatch.setattr(embedded_dbapi.importlib, "import_module", fake_import_module)

    conn = iris.dbapi.connect(mode="native", hostname="localhost", port=1972)

    assert calls == ["iris.dbapi"]
    assert conn["kwargs"]["hostname"] == "localhost"
    assert conn["kwargs"]["port"] == 1972


def test_dbapi_native_errors_when_official_module_missing(monkeypatch):
    def fake_import_module(name):
        raise ImportError(name)

    monkeypatch.setattr(embedded_dbapi.importlib, "import_module", fake_import_module)

    with pytest.raises(iris.dbapi.InterfaceError, match="iris.dbapi"):
        iris.dbapi.connect(mode="native", hostname="localhost", port=1972)
