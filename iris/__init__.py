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