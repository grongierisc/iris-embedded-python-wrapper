import importlib
import os
import sys
import warnings

from iris_utils import update_dynalib_path

_LOADER_PATH_WARNINGS_EMITTED = set()
_SHARED_LIBRARY_ERROR_MARKERS = (
    "cannot open shared object file",
    "dlopen(",
    "image not found",
    "library not loaded",
    "dll load failed",
    "undefined symbol",
    "symbol not found",
    "wrong elf class",
    "mach-o",
)


def get_install_dir_from_env():
    return os.environ.get('IRISINSTALLDIR') or os.environ.get('ISC_PACKAGE_INSTALLDIR')


def _append_sys_path(path):
    if path not in sys.path:
        sys.path.append(path)


def _push_sys_paths_front(paths):
    original = list(sys.path)
    for path in reversed(paths):
        while path in sys.path:
            sys.path.remove(path)
        sys.path.insert(0, path)
    return original


def _env_path_contains(env_var, path):
    target = os.path.normcase(os.path.realpath(os.fspath(path)))
    current_paths = os.environ.get(env_var, "")
    for entry in current_paths.split(os.pathsep):
        if not entry:
            continue
        candidate = os.path.normcase(os.path.realpath(entry))
        if candidate == target:
            return True
    return False


def format_loader_path_warning(install_dir):
    bin_dir = os.path.join(install_dir, 'bin')
    env_var = get_loader_path_env_var()
    return (
        f"IRIS embedded-local loading may fail because {env_var} does not "
        f"include {bin_dir}. Set {env_var} to include the IRIS bin directory "
        f"before Python starts; changing it after startup may be too late for "
        f"the dynamic loader."
    )


def warn_if_loader_path_unconfigured(install_dir):
    if sys.platform.startswith('win'):
        return

    bin_dir = os.path.join(install_dir, 'bin')
    env_var = get_loader_path_env_var()
    if _env_path_contains(env_var, bin_dir):
        return

    warning_key = (env_var, os.path.normcase(os.path.realpath(bin_dir)))
    if warning_key in _LOADER_PATH_WARNINGS_EMITTED:
        return
    _LOADER_PATH_WARNINGS_EMITTED.add(warning_key)

    warnings.warn(
        format_loader_path_warning(install_dir),
        RuntimeWarning,
        stacklevel=3,
    )


def configure_install_dir(path, *, warn_loader_path=False):
    if not path:
        raise ValueError("path must be a non-empty IRIS installation directory")

    install_dir = os.path.abspath(os.fspath(path))
    bin_dir = os.path.join(install_dir, 'bin')
    python_dir = os.path.join(install_dir, 'lib', 'python')

    if not os.path.isdir(install_dir):
        raise ValueError(
            f"IRIS installation directory does not exist: {install_dir}"
        )
    if not os.path.isdir(bin_dir):
        raise ValueError(
            f"IRIS installation directory is invalid: missing bin directory at {bin_dir}"
        )
    if not os.path.isdir(python_dir):
        raise ValueError(
            f"IRIS installation directory is invalid: missing embedded Python directory at {python_dir}"
        )

    _append_sys_path(bin_dir)
    _append_sys_path(python_dir)

    if warn_loader_path:
        warn_if_loader_path_unconfigured(install_dir)

    update_dynalib_path(bin_dir)
    return install_dir


def is_embedded_kernel():
    if bool(getattr(sys, "_embedded", 0)):
        return True

    public_iris = sys.modules.get('iris')
    if public_iris is None or getattr(public_iris, "__file__", None) is not None:
        return False

    return callable(getattr(public_iris, "__dict__", {}).get("cls"))


def get_preloaded_iris_kernel_module():
    public_iris = sys.modules.get('iris')
    if public_iris is None or getattr(public_iris, "__file__", None) is not None:
        return None
    if callable(getattr(public_iris, "__dict__", {}).get("cls")):
        return public_iris
    return None


def get_pythonint_module_name(version_info=None, os_name=None):
    version_info = version_info or sys.version_info
    os_name = os_name or os.name

    if os_name == 'nt':
        windows_modules = {
            9: 'pythonint39',
            10: 'pythonint310',
            11: 'pythonint311',
            12: 'pythonint312',
            13: 'pythonint313',
            14: 'pythonint314',
        }
        return windows_modules.get(version_info.minor)

    return 'pythonint'


def import_embedded_kernel_module():
    try:
        return importlib.import_module('irisep')
    except ModuleNotFoundError as exc:
        if exc.name != 'irisep':
            raise
        module = get_preloaded_iris_kernel_module()
        if module is not None:
            return module
        raise


def import_pythonint_module(module_name=None):
    module_name = module_name or get_pythonint_module_name()
    if module_name is None:
        raise RuntimeError(
            f"Embedded Python is not available for Python {sys.version_info.major}.{sys.version_info.minor}"
        )

    try:
        return importlib.import_module(name=module_name)
    except ModuleNotFoundError:
        if module_name == 'pythonint':
            raise
        return importlib.import_module(name='pythonint')


def get_pythonint_module_candidates(module_name=None):
    module_name = module_name or get_pythonint_module_name()
    if module_name is None:
        raise RuntimeError(
            f"Embedded Python is not available for Python {sys.version_info.major}.{sys.version_info.minor}"
        )

    candidates = [module_name]
    if module_name != 'pythonint':
        candidates.append('pythonint')
    return candidates


def get_loader_path_env_var(platform=None):
    platform = platform or sys.platform
    if platform.startswith('win'):
        return 'PATH'
    if platform == 'darwin':
        return 'DYLD_LIBRARY_PATH'
    return 'LD_LIBRARY_PATH'


def is_shared_library_import_error(exc):
    message = " ".join(str(arg) for arg in getattr(exc, "args", ()) if arg)
    if not message:
        message = str(exc)
    message = message.lower()
    return any(marker in message for marker in _SHARED_LIBRARY_ERROR_MARKERS)


def format_loader_path_import_error(install_dir, exc):
    bin_dir = os.path.join(install_dir, 'bin')
    env_var = get_loader_path_env_var()
    if sys.platform.startswith('win'):
        return (
            f"IRIS shared libraries could not be loaded while importing pythonint "
            f"from {install_dir}: {exc}. Make sure {bin_dir} is registered with "
            f"os.add_dll_directory() or present in PATH before importing IRIS."
        )

    return (
        f"IRIS shared libraries could not be loaded while importing pythonint "
        f"from {install_dir}: {exc}. On Unix, {env_var} must include {bin_dir} "
        f"before Python starts; changing it after startup may be too late for "
        f"the dynamic loader."
    )


def _is_path_under(path, root):
    try:
        path = os.path.normcase(os.path.realpath(os.fspath(path)))
        root = os.path.normcase(os.path.realpath(os.fspath(root)))
        return os.path.commonpath([path, root]) == root
    except (TypeError, ValueError):
        return False


def validate_pythonint_module_origin(module, install_dir):
    module_file = getattr(module, "__file__", None)
    bin_dir = os.path.join(install_dir, 'bin')
    python_dir = os.path.join(install_dir, 'lib', 'python')
    allowed_roots = (bin_dir, python_dir)

    if not module_file:
        raise RuntimeError(
            "Imported pythonint module has no __file__; cannot verify that it "
            f"belongs to explicit IRIS installation directory {install_dir}"
        )

    if any(_is_path_under(module_file, root) for root in allowed_roots):
        return module

    expected = " or ".join(allowed_roots)
    raise RuntimeError(
        f"Imported pythonint from {module_file}, which does not belong to "
        f"explicit IRIS installation directory {install_dir}. Expected it under "
        f"{expected}."
    )


def import_pythonint_module_from_install_dir(install_dir, module_name=None):
    candidates = get_pythonint_module_candidates(module_name)
    stale_modules = {
        name: sys.modules.pop(name)
        for name in candidates
        if name in sys.modules
    }
    importlib.invalidate_caches()
    original_sys_path = _push_sys_paths_front(
        (
            os.path.join(install_dir, 'bin'),
            os.path.join(install_dir, 'lib', 'python'),
        )
    )

    try:
        last_exc = None
        for candidate in candidates:
            try:
                module = importlib.import_module(name=candidate)
            except ModuleNotFoundError as exc:
                last_exc = exc
                continue
            except ImportError as exc:
                if is_shared_library_import_error(exc):
                    raise RuntimeError(
                        format_loader_path_import_error(install_dir, exc)
                    ) from exc
                last_exc = exc
                continue
            except OSError as exc:
                if is_shared_library_import_error(exc):
                    raise RuntimeError(
                        format_loader_path_import_error(install_dir, exc)
                    ) from exc
                raise

            return validate_pythonint_module_origin(module, install_dir)

        if last_exc is not None:
            raise last_exc
        raise ModuleNotFoundError(candidates[0])
    except Exception:
        for name, module in stale_modules.items():
            sys.modules.setdefault(name, module)
        raise
    finally:
        sys.path[:] = original_sys_path
