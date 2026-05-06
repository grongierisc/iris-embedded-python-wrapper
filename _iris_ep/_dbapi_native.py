from __future__ import annotations

import importlib
import importlib.metadata
import importlib.util
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any


_MISSING = object()


def _is_iris_module_name(name: str) -> bool:
    return name == "iris" or name.startswith("iris.")


def _snapshot_iris_modules() -> dict[str, Any]:
    return {name: module for name, module in sys.modules.items() if _is_iris_module_name(name)}


def _restore_iris_modules(saved_modules: dict[str, Any]) -> None:
    for name in [name for name in sys.modules if _is_iris_module_name(name)]:
        if name not in saved_modules:
            sys.modules.pop(name, None)
    sys.modules.update(saved_modules)


@contextmanager
def _isolated_iris_modules():
    saved_modules = _snapshot_iris_modules()
    try:
        for name in saved_modules:
            sys.modules.pop(name, None)
        yield
    finally:
        _restore_iris_modules(saved_modules)


def import_native_dbapi():
    saved_modules = _snapshot_iris_modules()
    try:
        return importlib.import_module("iris.dbapi")
    except ImportError as first_exc:
        _restore_iris_modules(saved_modules)
        try:
            return import_native_dbapi_from_distribution()
        except ImportError:
            raise first_exc


def import_native_dbapi_from_distribution():
    saved_modules = _snapshot_iris_modules()
    try:
        distribution = importlib.metadata.distribution("intersystems-irispython")
    except importlib.metadata.PackageNotFoundError as exc:
        raise ImportError("intersystems-irispython is not installed") from exc

    package_init = Path(distribution.locate_file("iris/__init__.py"))
    package_dir = package_init.parent
    if not package_init.is_file():
        raise ImportError("intersystems-irispython does not provide iris/__init__.py")

    try:
        public_iris = sys.modules.get("iris", _MISSING)
        official_iris = load_official_iris_package(package_init, package_dir)

        if public_iris is _MISSING:
            sys.modules["iris"] = official_iris
        else:
            attach_official_iris_sdk(public_iris, official_iris, package_dir)
            sys.modules["iris"] = public_iris

        return importlib.import_module("iris.dbapi")
    except Exception:
        _restore_iris_modules(saved_modules)
        raise


def load_official_iris_package(package_init: Path, package_dir: Path):
    with _isolated_iris_modules():
        spec = importlib.util.spec_from_file_location(
            "iris",
            package_init,
            submodule_search_locations=[str(package_dir)],
        )
        if spec is None or spec.loader is None:
            raise ImportError("Could not load official iris package")

        official_iris = importlib.util.module_from_spec(spec)
        sys.modules["iris"] = official_iris
        spec.loader.exec_module(official_iris)
        return official_iris


def attach_official_iris_sdk(public_iris: Any, official_iris: Any, package_dir: Path):
    package_path = str(package_dir)
    public_path = list(getattr(public_iris, "__path__", []))
    if package_path not in public_path:
        public_path.append(package_path)
        public_iris.__path__ = public_path

    for name, value in official_iris.__dict__.items():
        if name.startswith("__") or name in public_iris.__dict__:
            continue
        setattr(public_iris, name, value)


def restore_public_facade(native_dbapi: Any, facade: Any):
    parent_module = sys.modules.get("iris")
    if parent_module is None:
        return

    try:
        current_dbapi = getattr(parent_module, "dbapi", None)
    except Exception:
        return

    if current_dbapi is native_dbapi:
        try:
            setattr(parent_module, "dbapi", facade)
        except Exception:
            pass
