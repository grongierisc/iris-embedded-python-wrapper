import iris_embedded_python as iris
import _iris_ep._dbapi as embedded_dbapi
import _iris_ep._dbapi_native as native_dbapi_loader
import pytest
import sys
import threading
import types


def test_dbapi_native_uses_official_iris_dbapi(monkeypatch):
    iris.runtime.bind_backends(native_dbapi_module=None)
    calls = []

    class FakeNativeDBAPI:
        @staticmethod
        def connect(*args, **kwargs):
            return {"args": args, "kwargs": kwargs}

    def fake_import_module(name):
        calls.append(name)
        if name == "iris.dbapi":
            return FakeNativeDBAPI
        raise ImportError(name)

    monkeypatch.setattr(native_dbapi_loader.importlib, "import_module", fake_import_module)

    conn = iris.dbapi.connect(mode="native", hostname="localhost", port=1972)

    assert calls == ["iris.dbapi"]
    assert conn["kwargs"]["hostname"] == "localhost"
    assert conn["kwargs"]["port"] == 1972


def test_dbapi_native_import_preserves_public_facade(monkeypatch):
    iris.runtime.bind_backends(native_dbapi_module=None)
    calls = []
    facade = iris.dbapi
    parent_module = types.ModuleType("iris")
    parent_module.dbapi = facade

    class FakeNativeDBAPI:
        @staticmethod
        def connect(*args, **kwargs):
            return {"args": args, "kwargs": kwargs}

    def fake_import_module(name):
        calls.append(name)
        if name == "iris.dbapi":
            parent_module.dbapi = FakeNativeDBAPI
            return FakeNativeDBAPI
        raise ImportError(name)

    monkeypatch.setitem(sys.modules, "iris", parent_module)
    monkeypatch.setattr(native_dbapi_loader.importlib, "import_module", fake_import_module)

    conn = facade.connect(mode="native", hostname="localhost", port=1972)

    assert calls == ["iris.dbapi"]
    assert conn["kwargs"]["hostname"] == "localhost"
    assert parent_module.dbapi is facade


def test_dbapi_native_import_falls_back_to_installed_distribution(monkeypatch, tmp_path):
    package_dir = tmp_path / "iris"
    dbapi_dir = package_dir / "dbapi"
    dbapi_dir.mkdir(parents=True)
    (package_dir / "__init__.py").write_text('origin = "official"\n')
    (dbapi_dir / "__init__.py").write_text(
        "import iris\n\n"
        "def connect(*args, **kwargs):\n"
        "    return {'origin': iris.origin, 'args': args, 'kwargs': kwargs}\n"
    )

    class FakeDistribution:
        @staticmethod
        def locate_file(path):
            return tmp_path / path

    facade = types.ModuleType("iris")
    facade.dbapi = object()

    monkeypatch.setitem(sys.modules, "iris", facade)
    monkeypatch.delitem(sys.modules, "iris.dbapi", raising=False)
    monkeypatch.setattr(
        native_dbapi_loader.importlib.metadata,
        "distribution",
        lambda name: FakeDistribution(),
    )

    try:
        native_dbapi = embedded_dbapi._DBAPI._import_native_dbapi()
        conn = native_dbapi.connect(hostname="localhost")

        assert conn["origin"] == "official"
        assert conn["kwargs"]["hostname"] == "localhost"
        assert sys.modules["iris"] is facade
    finally:
        sys.modules.pop("iris.dbapi", None)


def test_dbapi_native_direct_import_failure_restores_iris_modules(monkeypatch):
    facade = types.ModuleType("iris")
    existing_submodule = types.ModuleType("iris.existing")

    def fake_import_module(name):
        if name == "iris.dbapi":
            sys.modules["iris.dbapi.partial"] = types.ModuleType("iris.dbapi.partial")
        raise ImportError(name)

    monkeypatch.setitem(sys.modules, "iris", facade)
    monkeypatch.setitem(sys.modules, "iris.existing", existing_submodule)
    monkeypatch.delitem(sys.modules, "iris.dbapi", raising=False)
    monkeypatch.delitem(sys.modules, "iris.dbapi.partial", raising=False)
    monkeypatch.setattr(native_dbapi_loader.importlib, "import_module", fake_import_module)
    monkeypatch.setattr(
        native_dbapi_loader.importlib.metadata,
        "distribution",
        lambda name: (_ for _ in ()).throw(
            native_dbapi_loader.importlib.metadata.PackageNotFoundError(name)
        ),
    )

    with pytest.raises(ImportError, match="iris.dbapi"):
        native_dbapi_loader.import_native_dbapi()

    assert sys.modules["iris"] is facade
    assert sys.modules["iris.existing"] is existing_submodule
    assert "iris.dbapi" not in sys.modules
    assert "iris.dbapi.partial" not in sys.modules


def test_dbapi_native_distribution_import_failure_restores_iris_modules(monkeypatch, tmp_path):
    package_dir = tmp_path / "iris"
    dbapi_dir = package_dir / "dbapi"
    dbapi_dir.mkdir(parents=True)
    (package_dir / "__init__.py").write_text('origin = "official"\n')
    (dbapi_dir / "__init__.py").write_text(
        "import sys\n"
        "import types\n\n"
        "sys.modules['iris.dbapi.partial'] = types.ModuleType('iris.dbapi.partial')\n"
        "raise ImportError('dbapi import failed')\n"
    )

    class FakeDistribution:
        @staticmethod
        def locate_file(path):
            return tmp_path / path

    facade = types.ModuleType("iris")
    facade.dbapi = object()
    existing_submodule = types.ModuleType("iris.existing")

    monkeypatch.setitem(sys.modules, "iris", facade)
    monkeypatch.setitem(sys.modules, "iris.existing", existing_submodule)
    monkeypatch.delitem(sys.modules, "iris.dbapi", raising=False)
    monkeypatch.delitem(sys.modules, "iris.dbapi.partial", raising=False)
    monkeypatch.setattr(
        native_dbapi_loader.importlib.metadata,
        "distribution",
        lambda name: FakeDistribution(),
    )

    with pytest.raises(ImportError, match="dbapi import failed"):
        native_dbapi_loader.import_native_dbapi_from_distribution()

    assert sys.modules["iris"] is facade
    assert sys.modules["iris.existing"] is existing_submodule
    assert "iris.dbapi" not in sys.modules
    assert "iris.dbapi.partial" not in sys.modules


def test_dbapi_native_module_isolation_supports_nested_use(monkeypatch):
    facade = types.ModuleType("iris")
    existing_submodule = types.ModuleType("iris.existing")
    monkeypatch.setitem(sys.modules, "iris", facade)
    monkeypatch.setitem(sys.modules, "iris.existing", existing_submodule)

    with native_dbapi_loader._isolated_iris_modules():
        assert "iris" not in sys.modules
        temporary = types.ModuleType("iris")
        sys.modules["iris"] = temporary

        with native_dbapi_loader._isolated_iris_modules():
            assert "iris" not in sys.modules

        assert sys.modules["iris"] is temporary

    assert sys.modules["iris"] is facade
    assert sys.modules["iris.existing"] is existing_submodule


def test_dbapi_native_module_isolation_serializes_threads(monkeypatch):
    facade = types.ModuleType("iris")
    monkeypatch.setitem(sys.modules, "iris", facade)
    first_entered = threading.Event()
    release_first = threading.Event()
    second_entered = threading.Event()
    failures = []

    def first_worker():
        try:
            with native_dbapi_loader._isolated_iris_modules():
                first_entered.set()
                if not release_first.wait(timeout=2):
                    raise AssertionError("timed out waiting to release isolation")
        except Exception as exc:
            failures.append(exc)

    def second_worker():
        try:
            if not first_entered.wait(timeout=2):
                raise AssertionError("first isolation did not start")
            with native_dbapi_loader._isolated_iris_modules():
                second_entered.set()
        except Exception as exc:
            failures.append(exc)

    first = threading.Thread(target=first_worker)
    second = threading.Thread(target=second_worker)
    first.start()
    assert first_entered.wait(timeout=2)
    second.start()

    assert not second_entered.wait(timeout=0.1)
    release_first.set()
    first.join(timeout=2)
    second.join(timeout=2)

    assert not first.is_alive()
    assert not second.is_alive()
    assert failures == []
    assert second_entered.is_set()
    assert sys.modules["iris"] is facade


def test_dbapi_native_errors_when_official_module_missing(monkeypatch):
    iris.runtime.bind_backends(native_dbapi_module=None)
    def fake_import_module(name):
        raise ImportError(name)

    monkeypatch.setattr(native_dbapi_loader.importlib, "import_module", fake_import_module)
    monkeypatch.setattr(
        native_dbapi_loader.importlib.metadata,
        "distribution",
        lambda name: (_ for _ in ()).throw(
            native_dbapi_loader.importlib.metadata.PackageNotFoundError(name)
        ),
    )

    with pytest.raises(iris.dbapi.InterfaceError, match="iris.dbapi"):
        iris.dbapi.connect(mode="native", hostname="localhost", port=1972)
