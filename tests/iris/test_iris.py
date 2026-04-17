import iris
import os
import pytest

def test_import_iris():
    import iris

    assert True

def test_runtime_can_be_forced_unavailable_without_install_dir():
    iris.runtime.configure(mode="auto", install_dir=None)

    assert iris.runtime.state == "unavailable"
    assert iris.runtime.embedded_available is False

def test_runtime_native_mode_requires_bound_iris_handle():
    iris.runtime.reset()

    with pytest.raises(RuntimeError, match="native mode"):
        iris.runtime.configure(mode="native")
        iris.cls("User.Bar")

    iris.runtime.reset()


def test_runtime_embedded_mode_requires_embedded_backend():
    iris.runtime.reset()

    with pytest.raises(RuntimeError):
        iris.runtime.configure(mode="embedded", install_dir=None)
        iris.cls("User.Bar")

    iris.runtime.reset()

