import os

import pytest
import iris_embedded_python as iris


def _embedded_runtime_ready() -> bool:
    ctx = iris.runtime.get()
    return ctx.embedded_available and ctx.state in ("embedded-kernel", "embedded-local")


def _native_connect_kwargs() -> dict:
    return {
        "hostname": os.getenv("IRIS_HOST", "localhost"),
        "port": int(os.getenv("IRIS_PORT", "1972")),
        "namespace": os.getenv("IRISNAMESPACE", "USER"),
        "username": os.getenv("IRISUSERNAME", "_SYSTEM"),
        "password": os.getenv("IRISPASSWORD", "SYS"),
    }


def test_dbapi_e2e_embedded_select_one_default_connect():
    assert _embedded_runtime_ready(), "Embedded runtime is required for e2e test"

    conn = iris.dbapi.connect()
    cur = conn.cursor()
    try:
        cur.execute("SELECT 1 AS result")
        row = cur.fetchone()
        assert row is not None
        assert row[0] == 1
    finally:
        cur.close()
        conn.close()


@pytest.fixture(params=["embedded", "remote"], ids=["embedded", "remote"])
def dbapi_mode(request):
    mode = request.param
    return mode


def _connect_for_mode(mode: str):
    if mode == "embedded":
        return iris.dbapi.connect(mode="embedded")
    if mode == "remote":
        return iris.dbapi.connect(mode="native", **_native_connect_kwargs())
    raise AssertionError(f"Unsupported dbapi mode: {mode}")


def test_dbapi_e2e_parameterized_select(dbapi_mode):
    conn = _connect_for_mode(dbapi_mode)
    cur = conn.cursor()
    try:
        cur.execute("SELECT ? AS result", (7,))
        row = cur.fetchone()
        assert row is not None
        assert row[0] == 7
    finally:
        cur.close()
        conn.close()


def test_dbapi_e2e_fetchmany_and_fetchall(dbapi_mode):
    conn = _connect_for_mode(dbapi_mode)
    cur = conn.cursor()
    try:
        cur.execute("SELECT 1 AS result UNION ALL SELECT 2 AS result")
        assert cur.fetchmany(1) == [(1,)]
        assert cur.fetchall() == [(2,)]
    finally:
        cur.close()
        conn.close()


def test_dbapi_e2e_cursor_for_loop_iteration(dbapi_mode):
    conn = _connect_for_mode(dbapi_mode)
    cur = conn.cursor()
    try:
        cur.execute("SELECT 1 AS result UNION ALL SELECT 2 AS result")
        rows = [row for row in cur]
        assert rows == [(1,), (2,)]
    finally:
        cur.close()
        conn.close()


def test_dbapi_e2e_with_connection_and_cursor(dbapi_mode):
    with _connect_for_mode(dbapi_mode) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 5 AS result")
            assert cur.fetchone() == (5,)

    with pytest.raises(iris.dbapi.InterfaceError):
        conn.cursor()


def test_dbapi_e2e_transaction_methods_and_close_behavior(dbapi_mode):
    conn = _connect_for_mode(dbapi_mode)
    conn.commit()
    conn.rollback()
    conn.close()

    with pytest.raises(iris.dbapi.InterfaceError):
        conn.commit()

    with pytest.raises(iris.dbapi.InterfaceError):
        conn.rollback()


def test_dbapi_e2e_parameterized_select_with_list_params(dbapi_mode):
    conn = _connect_for_mode(dbapi_mode)
    cur = conn.cursor()
    try:
        cur.execute("SELECT ? AS result", [9])
        row = cur.fetchone()
        assert row is not None
        assert row[0] == 9
    finally:
        cur.close()
        conn.close()


def test_dbapi_e2e_fetchone_returns_none_after_exhaustion(dbapi_mode):
    conn = _connect_for_mode(dbapi_mode)
    cur = conn.cursor()
    try:
        cur.execute("SELECT 1 AS result")
        assert cur.fetchone() == (1,)
        assert cur.fetchone() is None
    finally:
        cur.close()
        conn.close()


def test_dbapi_e2e_fetchmany_uses_arraysize_default(dbapi_mode):
    conn = _connect_for_mode(dbapi_mode)
    cur = conn.cursor()
    try:
        cur.arraysize = 2
        cur.execute("SELECT 1 AS result UNION ALL SELECT 2 AS result UNION ALL SELECT 3 AS result")
        assert cur.fetchmany() == [(1,), (2,)]
        assert cur.fetchmany() == [(3,)]
    finally:
        cur.close()
        conn.close()


def test_dbapi_e2e_fetchmany_larger_than_remaining_rows(dbapi_mode):
    conn = _connect_for_mode(dbapi_mode)
    cur = conn.cursor()
    try:
        cur.execute("SELECT 1 AS result UNION ALL SELECT 2 AS result")
        assert cur.fetchone() == (1,)
        assert cur.fetchmany(10) == [(2,)]
        assert cur.fetchone() is None
    finally:
        cur.close()
        conn.close()


def test_dbapi_e2e_execute_after_cursor_close_raises(dbapi_mode):
    conn = _connect_for_mode(dbapi_mode)
    cur = conn.cursor()
    try:
        cur.close()
        with pytest.raises(Exception):
            cur.execute("SELECT 1 AS result")
    finally:
        conn.close()


def test_dbapi_e2e_execute_after_connection_close_raises(dbapi_mode):
    conn = _connect_for_mode(dbapi_mode)
    cur = conn.cursor()
    try:
        conn.close()
        with pytest.raises(Exception):
            cur.execute("SELECT 1 AS result")
    finally:
        cur.close()
