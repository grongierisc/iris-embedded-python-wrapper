import importlib

from ._module_exports import copy_public_exports


def extend_official_driver_path(module_globals):
    try:
        from importlib import metadata
    except ImportError:
        try:
            import importlib_metadata as metadata
        except ImportError:
            return None

    try:
        distribution = metadata.distribution("intersystems-irispython")
    except metadata.PackageNotFoundError:
        return None

    package_init = distribution.locate_file("iris/__init__.py")
    try:
        package_dir = str(package_init.parent)
    except AttributeError:
        return None

    package_path = module_globals.get("__path__")
    if package_path is not None and package_dir not in package_path:
        package_path.append(package_dir)
    return package_dir


def load_driver_symbols(module_globals):
    extend_official_driver_path(module_globals)

    for module_name in ("iris._elsdk_", "iris._init_elsdk"):
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            continue

        copy_public_exports(module, module_globals)
        module_globals["_official_driver_loaded"] = True
        return True

    try:
        module = importlib.import_module("intersystems_iris")
    except ImportError:
        module_globals["_official_driver_loaded"] = False
        return False

    copy_public_exports(module, module_globals)
    module_globals["_official_driver_loaded"] = False
    return False


def is_wrapper_connect(candidate):
    return getattr(candidate, "__module__", "") == "_iris_ep._runtime_facade"


def rebind_wrapper_symbols(module_globals):
    driver_connect = module_globals.get("connect")
    if is_wrapper_connect(driver_connect):
        driver_connect = None
    module_globals["_driver_connect"] = driver_connect

    try:
        import iris_ep as iris_ep_module
    except ImportError:
        return

    if driver_connect is not None and getattr(iris_ep_module, "connect", None) is not driver_connect:
        runtime = getattr(iris_ep_module, "runtime", None)
        bind_backends = getattr(runtime, "bind_backends", None)
        if callable(bind_backends):
            bind_backends(native_connect=driver_connect)

    for name in ("runtime", "dbapi", "cls", "connect"):
        if hasattr(iris_ep_module, name):
            module_globals[name] = getattr(iris_ep_module, name)
