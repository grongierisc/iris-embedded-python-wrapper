import importlib
import os
import shutil
import subprocess
import sys
import textwrap

import pytest
import iris_embedded_python as iris


def test_embedded_runtime_is_available_from_python3():
    if getattr(sys, "_embedded", 0):
        pytest.skip("This e2e test is for python3 embedded-local execution")

    ctx = iris.runtime.get()
    if not ctx.embedded_available or ctx.state != "embedded-local":
        if os.getenv("IRIS_REQUIRE_EMBEDDED") == "1":
            pytest.fail("Embedded-local runtime is required from python3")
        pytest.skip("Embedded-local runtime is not available from python3")

    pythonint = importlib.import_module("pythonint")

    assert pythonint is not None
    assert iris.cls("%SYSTEM.Version").GetVersion()


def test_import_iris_from_iris_python_kernel_uses_wrapper():
    if os.getenv("IRIS_RUN_KERNEL_TEST") != "1":
        pytest.skip("iris python kernel import test is not enabled")

    iris_command = shutil.which("iris")
    if iris_command is None:
        pytest.fail("IRIS_RUN_KERNEL_TEST=1 but iris command is unavailable")

    app_dir = os.getenv("IRIS_APP_DIR", "/irisdev/app")
    env = os.environ.copy()
    env["PYTHONPATH"] = (
        f"{app_dir}{os.pathsep}{env['PYTHONPATH']}"
        if env.get("PYTHONPATH")
        else app_dir
    )

    script = textwrap.dedent(
        """
        import sys
        import iris

        assert getattr(sys, "_embedded", 0)
        assert hasattr(iris, "runtime")
        assert hasattr(iris, "connect")
        assert hasattr(iris, "cls")
        assert iris.runtime.get().state == "embedded-kernel"
        assert iris.cls("%SYSTEM.Version").GetVersion()
        print("KERNEL_IMPORT_OK")
        """
    )

    result = subprocess.run(
        [iris_command, "python", "iris"],
        input=script,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "KERNEL_IMPORT_OK" in result.stdout


def test_import_iris_from_session_python_shell_uses_wrapper():
    if os.getenv("IRIS_RUN_KERNEL_TEST") != "1":
        pytest.skip("iris session :py import test is not enabled")

    iris_command = shutil.which("iris")
    if iris_command is None:
        pytest.fail("IRIS_RUN_KERNEL_TEST=1 but iris command is unavailable")

    app_dir = os.getenv("IRIS_APP_DIR", "/irisdev/app")
    env = os.environ.copy()
    env["PYTHONPATH"] = (
        f"{app_dir}{os.pathsep}{env['PYTHONPATH']}"
        if env.get("PYTHONPATH")
        else app_dir
    )

    session_input = textwrap.dedent(
        """
        :py
        import sys
        import iris

        assert getattr(sys, "_embedded", 0)
        assert hasattr(iris, "runtime")
        assert hasattr(iris, "connect")
        assert hasattr(iris, "cls")
        assert iris.runtime.get().state == "embedded-kernel"
        assert iris.cls("%SYSTEM.Version").GetVersion()
        print("SESSION_PY_IMPORT_OK")
        quit()
        halt
        """
    )

    result = subprocess.run(
        [iris_command, "session", "iris"],
        input=session_input,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "SESSION_PY_IMPORT_OK" in result.stdout
