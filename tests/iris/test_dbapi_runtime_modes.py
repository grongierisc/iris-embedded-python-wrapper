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


def _install_fake_embedded_runtime(monkeypatch, tmp_path, fake_statement):
    install_dir = tmp_path / "iris"
    (install_dir / "bin").mkdir(parents=True)
    (install_dir / "lib" / "python").mkdir(parents=True)
    dynalib_paths = []

    fake_module = types.SimpleNamespace(
        cls=lambda name: FakeStatementFactory(fake_statement),
    )

    def fake_import_module(name):
        if name == "pythonint":
            return fake_module
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(_iris_ep._bootstrap.importlib, "import_module", fake_import_module)
    monkeypatch.setattr(_iris_ep._bootstrap, "update_dynalib_path", dynalib_paths.append)
    return install_dir, dynalib_paths, fake_module


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


def test_dbapi_connect_path_enables_embedded_runtime(monkeypatch, tmp_path):
    iris.runtime.reset()
    fake_statement = FakeStatement([(12, "path")])
    install_dir, dynalib_paths, fake_module = _install_fake_embedded_runtime(
        monkeypatch,
        tmp_path,
        fake_statement,
    )

    try:
        conn = iris.dbapi.connect(path=install_dir)
        cur = conn.cursor()
        cur.execute("select 1")

        assert iris.runtime.mode == "embedded"
        assert iris.runtime.get().install_dir == str(install_dir)
        assert iris.runtime.embedded_cls is fake_module.cls
        assert dynalib_paths == [str(install_dir / "bin")]
        assert cur.fetchone() == (12, "path")
    finally:
        iris.runtime.reset()


def test_dbapi_connect_path_allows_embedded_options(monkeypatch, tmp_path):
    iris.runtime.reset()
    fake_statement = FakeStatement([(1,)])
    install_dir, _, _ = _install_fake_embedded_runtime(
        monkeypatch,
        tmp_path,
        fake_statement,
    )

    try:
        conn = iris.dbapi.connect(
            path=install_dir,
            mode="embedded",
            namespace="USER",
            isolation_level=None,
        )

        assert conn._namespace == "USER"
        assert conn.isolation_level is None
    finally:
        iris.runtime.reset()


def test_dbapi_connect_path_rejects_native_mode(tmp_path):
    with pytest.raises(iris.dbapi.InterfaceError, match="mode='auto' or mode='embedded'"):
        iris.dbapi.connect(path=tmp_path, mode="native")


def test_dbapi_connect_path_rejects_native_arguments(tmp_path):
    with pytest.raises(iris.dbapi.InterfaceError, match="native connection arguments"):
        iris.dbapi.connect(path=tmp_path, hostname="localhost")

    with pytest.raises(iris.dbapi.InterfaceError, match="native connection arguments"):
        iris.dbapi.connect("localhost", path=tmp_path)


def test_dbapi_connect_path_rejects_unknown_options(tmp_path):
    with pytest.raises(iris.dbapi.InterfaceError, match="only accepts embedded options"):
        iris.dbapi.connect(path=tmp_path, timeout=10)
