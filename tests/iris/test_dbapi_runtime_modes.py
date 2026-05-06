import iris_embedded_python as iris
import _iris_ep
import pytest
import sys
import types

from tests.iris._dbapi_fakes import (
    FakeNamespaceProcess,
    FakeNamespaceStatementFactory,
    FakeStatement,
    FakeStatementFactory,
)


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

