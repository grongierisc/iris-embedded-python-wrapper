import sys
import types

from iris import _driver_loader


def test_driver_loader_prefers_official_sdk(monkeypatch):
    official_connect = object()
    official = types.SimpleNamespace(IRISConnection="official", connect=official_connect)
    community = types.SimpleNamespace(IRISConnection="community", connect=object())
    imported = []

    def fake_import_module(name):
        imported.append(name)
        if name == "iris._elsdk_":
            return official
        if name == "intersystems_iris":
            return community
        raise ImportError(name)

    monkeypatch.setattr(_driver_loader, "extend_official_driver_path", lambda module_globals: None)
    monkeypatch.setattr(_driver_loader.importlib, "import_module", fake_import_module)

    module_globals = {"__path__": []}

    assert _driver_loader.load_driver_symbols(module_globals) is True
    assert module_globals["_official_driver_loaded"] is True
    assert module_globals["IRISConnection"] == "official"
    assert module_globals["connect"] is official_connect
    assert "intersystems_iris" not in imported


def test_driver_loader_uses_community_only_when_official_unavailable(monkeypatch):
    community_connect = object()
    community = types.SimpleNamespace(IRISConnection="community", connect=community_connect)

    def fake_import_module(name):
        if name in ("iris._elsdk_", "iris._init_elsdk"):
            raise ImportError(name)
        if name == "intersystems_iris":
            return community
        raise AssertionError(name)

    monkeypatch.setattr(_driver_loader, "extend_official_driver_path", lambda module_globals: None)
    monkeypatch.setattr(_driver_loader.importlib, "import_module", fake_import_module)

    module_globals = {"__path__": []}

    assert _driver_loader.load_driver_symbols(module_globals) is False
    assert module_globals["_official_driver_loaded"] is False
    assert module_globals["IRISConnection"] == "community"
    assert module_globals["connect"] is community_connect


def test_driver_loader_rebinds_wrapper_symbols(monkeypatch):
    wrapper_connect = object()
    driver_connect = object()
    iris_ep_module = types.ModuleType("iris_ep")
    iris_ep_module.connect = wrapper_connect
    iris_ep_module.runtime = "runtime"
    iris_ep_module.dbapi = "dbapi"
    iris_ep_module.cls = "cls"

    monkeypatch.setitem(sys.modules, "iris_ep", iris_ep_module)

    module_globals = {"connect": driver_connect}

    _driver_loader.rebind_wrapper_symbols(module_globals)

    assert iris_ep_module._fallback_connect is driver_connect
    assert module_globals["_driver_connect"] is driver_connect
    assert module_globals["connect"] is wrapper_connect
    assert module_globals["runtime"] == "runtime"
    assert module_globals["dbapi"] == "dbapi"
    assert module_globals["cls"] == "cls"
