from __future__ import annotations

import importlib
import importlib.metadata
import importlib.util
import sys
from pathlib import Path
from typing import Any


_MISSING = object()


def import_native_dbapi():
    try:
        return importlib.import_module("iris.dbapi")
    except ImportError as first_exc:
        try:
            return import_native_dbapi_from_distribution()
        except ImportError:
            raise first_exc


def import_native_dbapi_from_distribution():
    try:
        distribution = importlib.metadata.distribution("intersystems-irispython")
    except importlib.metadata.PackageNotFoundError as exc:
        raise ImportError("intersystems-irispython is not installed") from exc

    package_init = Path(distribution.locate_file("iris/__init__.py"))
    package_dir = package_init.parent
    if not package_init.is_file():
        raise ImportError("intersystems-irispython does not provide iris/__init__.py")

    public_iris = sys.modules.get("iris", _MISSING)
    official_iris = load_official_iris_package(package_init, package_dir)

    if public_iris is _MISSING:
        sys.modules["iris"] = official_iris
    else:
        attach_official_iris_sdk(public_iris, official_iris, package_dir)
        sys.modules["iris"] = public_iris

    return importlib.import_module("iris.dbapi")


def load_official_iris_package(package_init: Path, package_dir: Path):
    saved_modules = {
        name: module
        for name, module in sys.modules.items()
        if name == "iris" or name.startswith("iris.")
    }

    for name in saved_modules:
        sys.modules.pop(name, None)

    try:
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
    finally:
        official_modules = {
            name: module
            for name, module in sys.modules.items()
            if name == "iris" or name.startswith("iris.")
        }
        for name in official_modules:
            sys.modules.pop(name, None)
        sys.modules.update(saved_modules)


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
