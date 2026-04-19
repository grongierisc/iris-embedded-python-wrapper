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


def test_runtime_reconfigure_clears_native_handles():
    iris.runtime.reset()

    class FakeIRISHandle:
        def classMethodValue(self, *args, **kwargs):
            raise NotImplementedError

    handle = FakeIRISHandle()

    iris.runtime.configure(mode="native", iris=handle, native_connection="CONN", dbapi="DBAPI")
    assert iris.runtime.mode == "native"
    assert iris.runtime.iris is handle
    assert iris.runtime.native_connection == "CONN"
    assert iris.runtime.dbapi == "DBAPI"

    iris.runtime.configure(mode="embedded", install_dir=None)

    assert iris.runtime.mode == "embedded"
    assert iris.runtime.state == "unavailable"
    assert iris.runtime.iris is None
    assert iris.runtime.native_connection is None
    assert iris.runtime.dbapi is None

    iris.runtime.reset()
