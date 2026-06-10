"""Shared startup hook and explicit installer for the IRIS wrapper facade.

InterSystems IRIS starts embedded Python with a built-in ``iris`` module already
present in ``sys.modules``.  In that ``embedded-kernel`` situation a later
``import iris`` returns the built-in module and never consults ``sys.path``, so
the wrapper facade (``dbapi``, ``runtime``, ``connect``, ``system``...) would be
missing.

This module exposes two entry points that patch the live ``iris`` module:

``install(force=False)``
    Explicit, idempotent, testable API for application code.  Safe to call from
    any runtime.  Returns the patched ``iris`` module.

``auto_install()``
    Guarded, exception-swallowing entry point used by startup triggers
    (the ``iris_ep.pth`` import-line and the legacy ``sitecustomize`` module).
    It only acts in the embedded-kernel runtime and is a cheap no-op otherwise.

This module is intentionally lightweight: importing it must not import the heavy
``_iris_ep`` package.  The wrapper is only imported lazily, inside the functions,
and only when a preloaded built-in ``iris`` module is detected.
"""

from __future__ import annotations

import logging
import sys
import warnings
from importlib import import_module


logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


_PUBLIC_WRAPPER_NAMES = ("runtime", "dbapi", "cls", "connect", "system")
_WRAPPER_MODULE_NAMES = ("iris_ep", "_iris_ep")
_INSTALLED_SENTINEL = "__iris_ep_installed__"


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


def install(*, force: bool = False):
    """Patch the live ``iris`` module with the wrapper facade.

    Idempotent and safe to call from any runtime (embedded-kernel,
    embedded-local, native-remote).  Returns the patched ``iris`` module.

    With ``force=False`` (the default), a previously completed install is a
    cheap no-op.  Pass ``force=True`` to re-run patching even if it already
    happened.
    """
    iris_mod = sys.modules.get("iris")
    if not force and getattr(iris_mod, _INSTALLED_SENTINEL, False):
        return iris_mod

    # Importing the wrapper builds/refreshes the facade.  In the package
    # runtimes (embedded-local / native-remote) this also patches an already
    # imported ``iris`` package via the facade's sync step.
    import_module("iris_ep")

    # In embedded-kernel a built-in ``iris`` is preloaded; patch it in place.
    _patch_preloaded_iris()

    iris_mod = sys.modules.get("iris")
    if iris_mod is None:
        # No ``iris`` imported yet outside a kernel: make the wrapper importable
        # as ``iris`` so the caller's next ``import iris`` resolves to it.
        iris_mod = import_module("iris")

    if iris_mod is not None:
        try:
            setattr(iris_mod, _INSTALLED_SENTINEL, True)
        except Exception as exc:  # pragma: no cover - read-only module guard
            logger.debug("Could not mark iris module as installed: %s", exc)

    return iris_mod


def auto_install() -> bool:
    """Guarded startup-hook entry point.

    Only acts in the embedded-kernel runtime; a cheap no-op elsewhere.  Never
    raises: any failure is downgraded to a ``RuntimeWarning`` so it cannot break
    interpreter startup.
    """
    try:
        return _patch_preloaded_iris()
    except Exception as exc:  # pragma: no cover - startup robustness guard
        warnings.warn(
            f"iris-embedded-python-wrapper could not patch the preloaded iris module: {exc}",
            RuntimeWarning,
            stacklevel=2,
        )
        return False
