import importlib
import os
import sys

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
