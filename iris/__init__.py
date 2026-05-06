# Embedded Python wrapper for InterSystems IRIS
try:
    from iris_ep import *
    from iris_ep import __getattr__
except ImportError:
    pass

try:
    from ._driver_loader import load_driver_symbols, rebind_wrapper_symbols
except ImportError:
    pass
else:
    load_driver_symbols(globals())
    # Re-bind unified wrapper symbols after wildcard driver imports.
    # Some drivers expose conflicting names that shadow the wrapper facade.
    rebind_wrapper_symbols(globals())
