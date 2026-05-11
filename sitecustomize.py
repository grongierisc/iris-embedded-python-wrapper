"""
Patch the preloaded IRIS embedded Python module when this package is on sys.path.

InterSystems IRIS starts embedded Python with a built-in ``iris`` module already
present in ``sys.modules``.  In that situation a later ``import iris`` cannot
load the wrapper package from PYTHONPATH or site-packages.  Python imports
``sitecustomize`` during startup, so this small guarded hook installs the
wrapper facade onto the preloaded module before user code runs.
"""

from __future__ import annotations

import sys
import warnings
from importlib import import_module


_PUBLIC_WRAPPER_NAMES = ("runtime", "dbapi", "cls", "connect", "system")
_WRAPPER_MODULE_NAMES = ("iris_ep", "_iris_ep")


def _clear_failed_wrapper_import() -> None:
    for module_name in _WRAPPER_MODULE_NAMES:
        sys.modules.pop(module_name, None)


def _is_preloaded_builtin_iris(module) -> bool:
    if module is None or getattr(module, "__file__", None) is not None:
        return False

    return callable(getattr(module, "__dict__", {}).get("cls"))


def _is_iris_embedded_kernel(public_iris) -> bool:
    return bool(getattr(sys, "_embedded", 0)) or _is_preloaded_builtin_iris(public_iris)


def _merge_public_names(public_iris, wrapper) -> None:
    wrapper_all = getattr(wrapper, "__all__", None)
    if not isinstance(wrapper_all, (list, tuple, set)):
        return

    existing_all = getattr(public_iris, "__all__", None)
    if isinstance(existing_all, (list, tuple, set)):
        public_names = [str(name) for name in existing_all]
    else:
        public_names = []

    for name in wrapper_all:
        name = str(name)
        if name not in public_names:
            public_names.append(name)

    public_iris.__all__ = public_names


def _install_wrapper_attrs(public_iris, wrapper) -> None:
    for name in _PUBLIC_WRAPPER_NAMES:
        if hasattr(wrapper, name):
            setattr(public_iris, name, getattr(wrapper, name))

    wrapper_getattr = getattr(wrapper, "__getattr__", None)
    if callable(wrapper_getattr):
        setattr(public_iris, "__getattr__", wrapper_getattr)

    _merge_public_names(public_iris, wrapper)


def _load_wrapper():
    public_iris = sys.modules.get("iris")
    import iris_ep as wrapper

    if _is_preloaded_builtin_iris(public_iris):
        _install_wrapper_attrs(public_iris, wrapper)

    return wrapper


class _LazyWrapperAttr:
    def __init__(self, name: str, fallback=None):
        self._name = name
        self._fallback = fallback

    def _target(self):
        return getattr(_load_wrapper(), self._name)

    def __getattr__(self, name):
        return getattr(self._target(), name)

    def __call__(self, *args, **kwargs):
        try:
            target = self._target()
        except ModuleNotFoundError:
            if callable(self._fallback):
                return self._fallback(*args, **kwargs)
            raise
        return target(*args, **kwargs)

    def __repr__(self):
        return f"<lazy iris-embedded-python-wrapper attribute {self._name}>"


def _install_lazy_wrapper_attrs(public_iris) -> None:
    public_dict = getattr(public_iris, "__dict__", {})
    for name in _PUBLIC_WRAPPER_NAMES:
        if name == "cls" and callable(public_dict.get("cls")):
            continue
        setattr(public_iris, name, _LazyWrapperAttr(name, public_dict.get(name)))


def _patch_preloaded_iris() -> bool:
    public_iris = sys.modules.get("iris")
    if public_iris is None and "iris" in sys.builtin_module_names:
        public_iris = import_module("iris")

    if not _is_iris_embedded_kernel(public_iris) or not _is_preloaded_builtin_iris(public_iris):
        return False

    try:
        wrapper = _load_wrapper()
    except ModuleNotFoundError as exc:
        if exc.name != "irisep":
            raise
        _clear_failed_wrapper_import()
        _install_lazy_wrapper_attrs(public_iris)
        return True

    _install_wrapper_attrs(public_iris, wrapper)
    return True


try:
    _patch_preloaded_iris()
except Exception as exc:  # pragma: no cover - startup robustness guard
    warnings.warn(
        f"iris-embedded-python-wrapper could not patch the preloaded iris module: {exc}",
        RuntimeWarning,
        stacklevel=2,
    )
