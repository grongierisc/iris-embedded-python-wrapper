import os
current_dir = os.path.dirname(os.path.abspath(__file__))

try:
    from iris_embedded_python import *
    from iris_embedded_python import __getattr__
except ImportError:
    pass

file_name_elsdk = os.path.join(current_dir, "_init_elsdk.py")
if os.path.exists(file_name_elsdk):
    from iris._init_elsdk import *

# newer versions are on _elsdk only, but we want to support older versions as well, so we try both
try:
    from iris._elsdk import *
except ImportError:
    pass