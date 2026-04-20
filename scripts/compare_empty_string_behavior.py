#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path
import sys
from dataclasses import dataclass
from typing import Any

# Make sure this checkout's wrapper package wins over any globally installed iris package.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import iris

WRAPPER_DBAPI = iris.dbapi
WRAPPER_RUNTIME = iris.runtime
WRAPPER_CLS = iris.cls


@dataclass
class ProbeResult:
    label: str
    value: Any = None
    error: str | None = None


def _embedded_runtime_ready() -> bool:
    ctx = WRAPPER_RUNTIME.get()
    return ctx.embedded_available and ctx.state in ("embedded-kernel", "embedded-local")


def _remote_connect_kwargs() -> dict[str, Any]:
    return {
        "hostname": os.getenv("IRIS_HOST", "localhost"),
        "port": int(os.getenv("IRIS_PORT", "1972")),
        "namespace": os.getenv("IRISNAMESPACE", "USER"),
        "username": os.getenv("IRISUSERNAME", "_SYSTEM"),
        "password": os.getenv("IRISPASSWORD", "SYS"),
    }


def _format_result(result: ProbeResult) -> str:
    if result.error is not None:
        return f"{result.label}: ERROR: {result.error}"
    return f"{result.label}: value={result.value!r} type={type(result.value).__name__}"


def _probe_dbapi(mode: str, sql: str, params: list[Any] | None) -> ProbeResult:
    label = f"{mode} dbapi"
    connect_kwargs = _remote_connect_kwargs() if mode == "remote" else {}

    try:
        conn = WRAPPER_DBAPI.connect(mode="native" if mode == "remote" else "embedded", **connect_kwargs)
    except Exception as exc:
        return ProbeResult(label=label, error=f"connect failed: {exc}")

    cur = conn.cursor()
    try:
        if params is None:
            cur.execute(sql)
        else:
            cur.execute(sql, params)
        row = cur.fetchone()
        if row is None:
            return ProbeResult(label=label, error="no row returned")
        return ProbeResult(label=label, value=row[0])
    except Exception as exc:
        return ProbeResult(label=label, error=str(exc))
    finally:
        cur.close()
        conn.close()


def _probe_object(mode: str) -> ProbeResult:
    label = f"{mode} object"
    conn = None
    try:
        if mode == "embedded":
            if not _embedded_runtime_ready():
                return ProbeResult(label=label, error="embedded runtime unavailable")
            WRAPPER_RUNTIME.configure(mode="embedded")
        else:
            kwargs = _remote_connect_kwargs()
            conn = iris.createConnection(
                kwargs["hostname"],
                kwargs["port"],
                kwargs["namespace"],
                kwargs["username"],
                kwargs["password"],
            )
            WRAPPER_RUNTIME.configure(native_connection=conn)

        obj = WRAPPER_CLS("Ens.StringRequest")._New()
        obj.StringValue = ""
        return ProbeResult(label=label, value=obj.StringValue)
    except Exception as exc:
        return ProbeResult(label=label, error=str(exc))
    finally:
        WRAPPER_RUNTIME.reset()
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def _print_section(title: str, results: list[ProbeResult]) -> None:
    print(title)
    for result in results:
        print(f"  {_format_result(result)}")
    print()


def main() -> int:
    print("IRIS empty-string parity probe")
    print(f"embedded runtime ready: {_embedded_runtime_ready()}")
    print(f"remote target: {_remote_connect_kwargs()}")
    print()

    dbapi_param_results = []
    if _embedded_runtime_ready():
        dbapi_param_results.append(_probe_dbapi("embedded", "SELECT ? AS value", [""]))
    else:
        dbapi_param_results.append(ProbeResult(label="embedded dbapi", error="embedded runtime unavailable"))
    dbapi_param_results.append(_probe_dbapi("remote", "SELECT ? AS value", [""]))
    _print_section("DB-API parameterized SELECT ? AS value", dbapi_param_results)

    dbapi_literal_results = []
    if _embedded_runtime_ready():
        dbapi_literal_results.append(_probe_dbapi("embedded", "SELECT '' AS value", None))
    else:
        dbapi_literal_results.append(ProbeResult(label="embedded dbapi", error="embedded runtime unavailable"))
    dbapi_literal_results.append(_probe_dbapi("remote", "SELECT '' AS value", None))
    _print_section("DB-API literal SELECT '' AS value", dbapi_literal_results)

    dbapi_null_results = []
    if _embedded_runtime_ready():
        dbapi_null_results.append(_probe_dbapi("embedded", "SELECT CAST(NULL AS VARCHAR(10)) AS value", None))
    else:
        dbapi_null_results.append(ProbeResult(label="embedded dbapi", error="embedded runtime unavailable"))
    dbapi_null_results.append(_probe_dbapi("remote", "SELECT CAST(NULL AS VARCHAR(10)) AS value", None))
    _print_section("DB-API literal SELECT CAST(NULL AS VARCHAR(10)) AS value", dbapi_null_results)

    object_results = [_probe_object("embedded"), _probe_object("remote")]
    _print_section("Object API Ens.StringRequest.StringValue round-trip", object_results)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
