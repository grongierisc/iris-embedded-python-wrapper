import os
import subprocess
import sys
from functools import lru_cache

import pytest
import iris_embedded_python as iris


def _embedded_runtime_ready() -> bool:
    ctx = iris.runtime.get()
    return ctx.embedded_available and ctx.state in ("embedded-kernel", "embedded-local")


def _embedded_required() -> bool:
    return os.getenv("IRIS_REQUIRE_EMBEDDED") == "1"


def _require_embedded_runtime():
    if not _embedded_runtime_ready():
        if _embedded_required():
            pytest.fail("Embedded runtime is required for this e2e test")
        pytest.skip("Embedded runtime is required for this e2e test")


def _format_status(value) -> str:
    text = str(value).replace("\x00", "\\0")
    text = "".join(char if char.isprintable() else " " for char in text)
    return " ".join(text.split())[:200]


@lru_cache(maxsize=1)
def _embedded_sql_ready() -> tuple[bool, str]:
    if not _embedded_runtime_ready():
        return False, "embedded runtime is unavailable"

    try:
        statement = iris.cls("%SQL.Statement")._New()
        status = statement._Prepare("SELECT 1")
    except Exception as exc:
        return False, f"%SQL.Statement probe failed: {exc}"

    if status != 1:
        return False, f"%SQL.Statement cannot prepare SELECT in this image: {_format_status(status)}"

    return True, ""


def _require_embedded_dbapi_sql():
    ready, reason = _embedded_sql_ready()
    if not ready:
        if os.getenv("IRIS_REQUIRE_EMBEDDED_SQL") == "1":
            pytest.fail(reason)
        pytest.skip(reason)


def _dbapi_modes() -> list[str]:
    configured = os.getenv("IRIS_E2E_MODES")
    if configured:
        modes = [mode.strip() for mode in configured.split(",") if mode.strip()]
        invalid_modes = sorted(set(modes) - {"embedded", "remote"})
        if invalid_modes:
            raise ValueError(f"Unsupported IRIS_E2E_MODES values: {', '.join(invalid_modes)}")
        return modes
    return ["embedded", "remote"]


def _remote_mode_enabled() -> bool:
    return "remote" in _dbapi_modes()


def _native_connect_kwargs() -> dict:
    return {
        "hostname": os.getenv("IRIS_HOST", "localhost"),
        "port": int(os.getenv("IRIS_PORT", "1972")),
        "namespace": os.getenv("IRISNAMESPACE", "USER"),
        "username": os.getenv("IRISUSERNAME", "_SYSTEM"),
        "password": os.getenv("IRISPASSWORD", "SYS"),
    }


def test_dbapi_e2e_embedded_select_one_default_connect():
    _require_embedded_runtime()
    _require_embedded_dbapi_sql()

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


def test_connect_path_e2e_enables_embedded_without_install_env():
    _require_embedded_runtime()

    install_dir = (
        os.getenv("IRISINSTALLDIR")
        or os.getenv("ISC_PACKAGE_INSTALLDIR")
        or "/usr/irissys"
    )
    env = os.environ.copy()
    env.pop("IRISINSTALLDIR", None)
    env.pop("ISC_PACKAGE_INSTALLDIR", None)

    script = f"""
import iris

ctx = iris.connect(path={install_dir!r})
assert ctx.mode == "embedded"
assert ctx.install_dir == {install_dir!r}
assert ctx.embedded_available is True
version = iris.cls("%SYSTEM.Version").GetVersion()
assert version
print(version)
"""

    result = subprocess.run(
        [sys.executable, "-c", script],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr


@pytest.fixture(params=_dbapi_modes())
def dbapi_mode(request):
    mode = request.param
    if mode == "embedded" and not _embedded_runtime_ready():
        pytest.skip("Embedded runtime is required for embedded DB-API e2e tests")
    if mode == "embedded":
        _require_embedded_dbapi_sql()
    return mode


def _connect_for_mode(mode: str):
    if mode == "embedded":
        return iris.dbapi.connect(mode="embedded")
    if mode == "remote":
        return iris.dbapi.connect(mode="native", **_native_connect_kwargs())
    raise AssertionError(f"Unsupported dbapi mode: {mode}")


def _tuple_row(row):
    if row is None:
        return None
    return tuple(row)


def _tuple_rows(rows):
    return [tuple(row) for row in rows]


def _fetch_scalar(mode: str, sql: str, params=None):
    conn = _connect_for_mode(mode)
    cur = conn.cursor()
    try:
        if params is None:
            cur.execute(sql)
        else:
            cur.execute(sql, params)
        row = cur.fetchone()
        assert row is not None
        return row[0]
    finally:
        cur.close()
        conn.close()


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
        assert _tuple_rows(cur.fetchmany(1)) == [(1,)]
        assert _tuple_rows(cur.fetchall()) == [(2,)]
    finally:
        cur.close()
        conn.close()


def test_dbapi_e2e_cursor_for_loop_iteration(dbapi_mode):
    conn = _connect_for_mode(dbapi_mode)
    cur = conn.cursor()
    try:
        cur.execute("SELECT 1 AS result UNION ALL SELECT 2 AS result")
        rows = _tuple_rows(row for row in cur)
        assert rows == [(1,), (2,)]
    finally:
        cur.close()
        conn.close()


def test_dbapi_e2e_with_connection_and_cursor(dbapi_mode):
    with _connect_for_mode(dbapi_mode) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 5 AS result")
            assert _tuple_row(cur.fetchone()) == (5,)

    with pytest.raises(Exception):
        conn.cursor()


def test_dbapi_e2e_transaction_methods_and_close_behavior(dbapi_mode):
    conn = _connect_for_mode(dbapi_mode)
    conn.commit()
    conn.rollback()
    conn.close()

    with pytest.raises(Exception):
        conn.commit()

    with pytest.raises(Exception):
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
        assert _tuple_row(cur.fetchone()) == (1,)
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
        assert _tuple_rows(cur.fetchmany()) == [(1,), (2,)]
        assert _tuple_rows(cur.fetchmany()) == [(3,)]
    finally:
        cur.close()
        conn.close()


def test_dbapi_e2e_fetchmany_larger_than_remaining_rows(dbapi_mode):
    conn = _connect_for_mode(dbapi_mode)
    cur = conn.cursor()
    try:
        cur.execute("SELECT 1 AS result UNION ALL SELECT 2 AS result")
        assert _tuple_row(cur.fetchone()) == (1,)
        assert _tuple_rows(cur.fetchmany(10)) == [(2,)]
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


def test_dbapi_e2e_null_scalar_matches_between_embedded_and_remote():
    _require_embedded_runtime()
    _require_embedded_dbapi_sql()
    if not _remote_mode_enabled():
        pytest.skip("Remote DB-API mode is not enabled")

    embedded_value = _fetch_scalar("embedded", "SELECT CAST(NULL AS VARCHAR(10)) AS value")
    remote_value = _fetch_scalar("remote", "SELECT CAST(NULL AS VARCHAR(10)) AS value")

    assert embedded_value == remote_value
    assert embedded_value is None


def test_dbapi_e2e_empty_string_literal_matches_between_embedded_and_remote():
    _require_embedded_runtime()
    _require_embedded_dbapi_sql()
    if not _remote_mode_enabled():
        pytest.skip("Remote DB-API mode is not enabled")

    embedded_value = _fetch_scalar("embedded", "SELECT '' AS value")
    remote_value = _fetch_scalar("remote", "SELECT '' AS value")

    assert embedded_value == remote_value
    assert embedded_value == ""


def test_dbapi_e2e_empty_string_parameter_matches_between_embedded_and_remote():
    _require_embedded_runtime()
    _require_embedded_dbapi_sql()
    if not _remote_mode_enabled():
        pytest.skip("Remote DB-API mode is not enabled")

    embedded_value = _fetch_scalar("embedded", "SELECT ? AS value", [""])
    remote_value = _fetch_scalar("remote", "SELECT ? AS value", [""])

    assert embedded_value == remote_value
    assert embedded_value == ""
