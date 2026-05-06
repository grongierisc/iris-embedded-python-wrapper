import importlib.metadata
import os
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]


def _fresh_python(script: str, tmp_path, extra_env=None):
    env = os.environ.copy()
    env.pop("IRISINSTALLDIR", None)
    env.pop("ISC_PACKAGE_INSTALLDIR", None)
    env.pop("ISC_CPF_MERGE_FILE", None)
    env["PYTHONPATH"] = (
        f"{REPO_ROOT}{os.pathsep}{env['PYTHONPATH']}"
        if env.get("PYTHONPATH")
        else str(REPO_ROOT)
    )
    if extra_env:
        env.update(extra_env)

    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(script)],
        cwd=tmp_path,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _assert_fresh_python_ok(result):
    assert result.returncode == 0, result.stdout + result.stderr


def test_import_iris_contract_from_outside_repo(tmp_path):
    result = _fresh_python(
        f"""
        import os
        from pathlib import Path
        import sys

        before = os.getcwd()
        repo = Path({str(REPO_ROOT)!r}).resolve()

        import iris
        import iris_ep
        import iris_embedded_python

        assert Path(iris.__file__).resolve() == repo / "iris" / "__init__.py", iris.__file__
        assert sys.modules["iris"] is iris
        assert hasattr(iris, "runtime")
        assert hasattr(iris, "dbapi")
        assert hasattr(iris, "cls")
        assert hasattr(iris, "connect")
        assert not hasattr(iris_ep, "_original_cls")
        assert not hasattr(iris_ep, "_fallback_connect")
        assert iris.runtime is iris_ep.runtime
        assert iris_embedded_python.runtime is iris.runtime
        assert os.getcwd() == before
        print("IMPORT_CONTRACT_OK")
        """,
        tmp_path,
    )

    _assert_fresh_python_ok(result)
    assert "IMPORT_CONTRACT_OK" in result.stdout


def test_import_iris_without_install_dir_does_not_probe_pythonint(tmp_path):
    result = _fresh_python(
        """
        import importlib

        calls = []
        real_import_module = importlib.import_module

        def tracking_import_module(name, *args, **kwargs):
            calls.append(name)
            return real_import_module(name, *args, **kwargs)

        importlib.import_module = tracking_import_module
        try:
            import iris
        finally:
            importlib.import_module = real_import_module

        assert "pythonint" not in calls, calls
        assert not any(name.startswith("pythonint") for name in calls), calls
        print("NO_PYTHONINT_PROBE_OK")
        """,
        tmp_path,
    )

    _assert_fresh_python_ok(result)
    assert "NO_PYTHONINT_PROBE_OK" in result.stdout


@pytest.mark.skipif(sys.platform.startswith("win"), reason="Unix loader-path warning")
@pytest.mark.parametrize("install_env", ["IRISINSTALLDIR", "ISC_PACKAGE_INSTALLDIR"])
def test_import_iris_with_install_env_warns_when_loader_path_wrong(tmp_path, install_env):
    install_dir = tmp_path / "iris"
    other_dir = tmp_path / "other"
    (install_dir / "bin").mkdir(parents=True)
    (install_dir / "lib" / "python").mkdir(parents=True)
    other_dir.mkdir()
    env_var = "DYLD_LIBRARY_PATH" if sys.platform == "darwin" else "LD_LIBRARY_PATH"

    result = _fresh_python(
        """
        import warnings

        warnings.simplefilter("always", RuntimeWarning)
        import iris

        assert iris.runtime.get().install_dir
        print("INSTALL_ENV_LOADER_WARNING_OK")
        """,
        tmp_path,
        extra_env={
            install_env: str(install_dir),
            env_var: str(other_dir),
        },
    )

    _assert_fresh_python_ok(result)
    assert "INSTALL_ENV_LOADER_WARNING_OK" in result.stdout
    assert f"{env_var} does not include {install_dir / 'bin'}" in result.stderr


def test_native_dbapi_import_contract_preserves_wrapper_parent(tmp_path):
    try:
        importlib.metadata.distribution("intersystems-irispython")
    except importlib.metadata.PackageNotFoundError:
        pytest.skip("intersystems-irispython is not installed")

    result = _fresh_python(
        """
        import sys
        import iris

        wrapper = iris
        facade = iris.dbapi
        native_dbapi = facade._import_native_dbapi()

        assert native_dbapi.__name__ == "iris.dbapi"

        def fake_connect(*args, **kwargs):
            return {"args": args, "kwargs": kwargs}

        native_dbapi.connect = fake_connect
        conn = facade.connect(mode="native", hostname="localhost", port=1972)

        assert conn["kwargs"]["hostname"] == "localhost"
        assert sys.modules["iris"] is wrapper
        assert iris.dbapi is facade
        assert iris.dbapi is not native_dbapi
        print("NATIVE_DBAPI_CONTRACT_OK")
        """,
        tmp_path,
    )

    _assert_fresh_python_ok(result)
    assert "NATIVE_DBAPI_CONTRACT_OK" in result.stdout
