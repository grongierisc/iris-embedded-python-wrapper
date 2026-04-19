# Embedded Python wrapper for InterSystems IRIS
try:
    from iris_ep import *
    from iris_ep import __getattr__
except ImportError:
    pass

# Official driver
try:
    from iris._elsdk_ import *
except ImportError:
    pass

# Old version of official driver, still used in some environments
try:
    from iris._init_elsdk import *
except ImportError:
    pass

# Community driver
try:
    from intersystems_iris import *
except ImportError:
    pass

# Re-bind unified wrapper symbols after wildcard driver imports.
# Some drivers expose a conflicting dbapi module that shadows the wrapper facade.
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
