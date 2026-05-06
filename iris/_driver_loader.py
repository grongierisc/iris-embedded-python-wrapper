import importlib


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


def copy_public_exports(module, module_globals):
    exported_names = getattr(module, "__all__", None)
    if exported_names is None:
        exported_names = [name for name in module.__dict__ if not name.startswith("_")]

    for name in exported_names:
        module_globals[name] = getattr(module, name)


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


def rebind_wrapper_symbols(module_globals):
    driver_connect = module_globals.get("connect")
    module_globals["_driver_connect"] = driver_connect

    try:
        import iris_ep as iris_ep_module
    except ImportError:
        return

    if driver_connect is not None and getattr(iris_ep_module, "connect", None) is not driver_connect:
        iris_ep_module._fallback_connect = driver_connect

    for name in ("runtime", "dbapi", "cls", "connect"):
        if hasattr(iris_ep_module, name):
            module_globals[name] = getattr(iris_ep_module, name)
