# Embedded Python wrapper for InterSystems IRIS
try:
    from iris_ep import *
    from iris_ep import __getattr__
except ImportError:
    pass

_official_driver_loaded = False


def _extend_official_driver_path():
    try:
        from importlib import metadata
    except ImportError:
        try:
            import importlib_metadata as metadata
        except ImportError:
            return

    try:
        distribution = metadata.distribution("intersystems-irispython")
    except metadata.PackageNotFoundError:
        return

    package_init = distribution.locate_file("iris/__init__.py")
    try:
        package_dir = str(package_init.parent)
    except AttributeError:
        return

    package_path = globals().get("__path__")
    if package_path is not None and package_dir not in package_path:
        package_path.append(package_dir)


_extend_official_driver_path()

# Official driver
try:
    from iris._elsdk_ import *
    _official_driver_loaded = True
except ImportError:
    pass

# Old version of official driver, still used in some environments
if not _official_driver_loaded:
    try:
        from iris._init_elsdk import *
        _official_driver_loaded = True
    except ImportError:
        pass

# Community driver fallback. Do not import it after the official SDK because
# it exposes overlapping names such as IRISConnection without DB-API support.
if not _official_driver_loaded:
    try:
        from intersystems_iris import *
    except ImportError:
        pass

# Re-bind unified wrapper symbols after wildcard driver imports.
# Some drivers expose a conflicting dbapi module that shadows the wrapper facade.
try:
    _driver_connect = connect
except NameError:
    _driver_connect = None

try:
    import iris_ep as _iris_ep

    if _driver_connect is not None and getattr(_iris_ep, "connect", None) is not _driver_connect:
        _iris_ep._fallback_connect = _driver_connect

    if hasattr(_iris_ep, "runtime"):
        runtime = _iris_ep.runtime
    if hasattr(_iris_ep, "dbapi"):
        dbapi = _iris_ep.dbapi
    if hasattr(_iris_ep, "cls"):
        cls = _iris_ep.cls
    if hasattr(_iris_ep, "connect"):
        connect = _iris_ep.connect
except ImportError:
    pass
