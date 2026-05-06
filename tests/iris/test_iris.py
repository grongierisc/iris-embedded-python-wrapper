import iris
import _iris_ep
import os
import pytest
import sys
import types


_MISSING = object()


def _snapshot_module_attrs(*names):
    modules = [
        module for module in (
            iris,
            _iris_ep,
            sys.modules.get("iris_ep"),
            sys.modules.get("iris_embedded_python"),
        )
        if module is not None
    ]
    return {
        (module, name): getattr(module, name, _MISSING)
        for module in modules
        for name in names
    }


def _restore_module_attrs(snapshot):
    for (module, name), value in snapshot.items():
        if value is _MISSING:
            try:
                delattr(module, name)
            except AttributeError:
                pass
        else:
            setattr(module, name, value)

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
    module_attrs = _snapshot_module_attrs("system", "__getattr__")

    install_dir = tmp_path / "iris"
    (install_dir / "bin").mkdir(parents=True)
    (install_dir / "lib" / "python").mkdir(parents=True)
    dynalib_paths = []

    class FakeVersion:
        @staticmethod
        def GetVersion():
            return "IRIS fake version"

    def fake_cls(class_name):
        if class_name == "%SYSTEM.Version":
            return FakeVersion
        return {"class": class_name}

    fake_module = types.SimpleNamespace(
        cls=fake_cls,
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
        assert iris.system.Version.GetVersion() == "IRIS fake version"
        with pytest.raises(AttributeError):
            iris.not_present
        assert iris.connect(label="runtime-owned") == {
            "args": (),
            "kwargs": {"label": "runtime-owned"},
        }
    finally:
        iris.runtime.reset()
        _restore_module_attrs(module_attrs)


def test_connect_path_rejects_native_arguments(tmp_path):
    with pytest.raises(TypeError, match="path"):
        iris.connect("localhost", path=tmp_path)


def test_connect_path_rejects_missing_install_dir(monkeypatch, tmp_path):
    missing_dir = tmp_path / "missing-iris"
    import_calls = []
    dynalib_paths = []

    monkeypatch.setattr(
        _iris_ep._bootstrap.importlib,
        "import_module",
        lambda name: import_calls.append(name),
    )
    monkeypatch.setattr(_iris_ep._bootstrap, "update_dynalib_path", dynalib_paths.append)

    with pytest.raises(ValueError, match="does not exist"):
        iris.connect(path=missing_dir)

    assert import_calls == []
    assert dynalib_paths == []


def test_connect_path_rejects_invalid_install_layout(monkeypatch, tmp_path):
    install_dir = tmp_path / "iris"
    install_dir.mkdir()
    import_calls = []
    dynalib_paths = []

    monkeypatch.setattr(
        _iris_ep._bootstrap.importlib,
        "import_module",
        lambda name: import_calls.append(name),
    )
    monkeypatch.setattr(_iris_ep._bootstrap, "update_dynalib_path", dynalib_paths.append)

    with pytest.raises(ValueError, match="missing bin directory"):
        iris.connect(path=install_dir)

    (install_dir / "bin").mkdir()

    with pytest.raises(ValueError, match="missing embedded Python directory"):
        iris.connect(path=install_dir)

    assert import_calls == []
    assert dynalib_paths == []
