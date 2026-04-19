try:
    from iris_ep import *
    from iris_ep import __getattr__
except ImportError:
    pass

try:
    import iris_ep as _iris_ep

    if hasattr(_iris_ep, "runtime"):
        runtime = _iris_ep.runtime
    if hasattr(_iris_ep, "dbapi"):
        dbapi = _iris_ep.dbapi
    if hasattr(_iris_ep, "cls"):
        cls = _iris_ep.cls
except ImportError:
    pass
