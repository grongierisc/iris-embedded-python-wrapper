import iris_embedded_python as iris
import _iris_ep
import types

from tests.iris._dbapi_fakes import (
    FakeStatement,
    FakeStatementAttrOnly,
    FakeStatementFactory,
    FakeStatementGetDataOnly,
    FakeStatementNoColumnCount,
    FakeStatementNoColumnCountInfinite,
)


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

