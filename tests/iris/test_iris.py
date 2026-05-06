import iris
import _iris_ep
import os
import pytest
import types

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


def test_connect_path_enables_embedded_runtime(monkeypatch, tmp_path):
    iris.runtime.reset()

    install_dir = tmp_path / "iris"
    (install_dir / "bin").mkdir(parents=True)
    (install_dir / "lib" / "python").mkdir(parents=True)
    dynalib_paths = []

    fake_module = types.SimpleNamespace(
        cls=lambda class_name: {"class": class_name},
        connect=lambda *args, **kwargs: {"args": args, "kwargs": kwargs},
    )

    def fake_import_module(name):
        if name == "pythonint":
            return fake_module
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(_iris_ep._bootstrap.importlib, "import_module", fake_import_module)
    monkeypatch.setattr(_iris_ep._bootstrap, "update_dynalib_path", dynalib_paths.append)

    try:
        context = iris.connect(path=install_dir)

        assert context.mode == "embedded"
        assert context.install_dir == str(install_dir)
        assert context.embedded_available is True
        assert context.embedded_module is fake_module
        assert context.embedded_cls is fake_module.cls
        assert context.embedded_connect is fake_module.connect
        assert dynalib_paths == [str(install_dir / "bin")]
        assert iris.cls("User.Foo") == {"class": "User.Foo"}
        assert iris.connect(label="runtime-owned") == {
            "args": (),
            "kwargs": {"label": "runtime-owned"},
        }
    finally:
        iris.runtime.reset()


def test_connect_path_rejects_native_arguments(tmp_path):
    with pytest.raises(TypeError, match="path"):
        iris.connect("localhost", path=tmp_path)
