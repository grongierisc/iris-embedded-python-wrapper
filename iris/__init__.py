import os
import sys
import importlib

from .iris_ipm import ipm
from .iris_utils import update_dynalib_path

# check for install dir in environment
# environment to check is IRISINSTALLDIR
# if not found, raise exception and exit
# ISC_PACKAGE_INSTALLDIR - defined by default in Docker images
installdir = os.environ.get('IRISINSTALLDIR') or os.environ.get('ISC_PACKAGE_INSTALLDIR')
if installdir is None:
        raise Exception("""Cannot find InterSystems IRIS installation directory
    Please set IRISINSTALLDIR environment variable to the InterSystems IRIS installation directory""")

__sysversion_info = sys.version_info
__syspath = sys.path
__osname = os.name

# join the install dir with the bin directory
__syspath.append(os.path.join(installdir, 'bin'))
# also append lib/python
__syspath.append(os.path.join(installdir, 'lib', 'python'))

# update the dynalib path
update_dynalib_path(os.path.join(installdir, 'bin'))

# save working directory
__ospath = os.getcwd()

__irispythonint = None

if __osname=='nt':
    if __sysversion_info.minor==9:
        __irispythonint = 'pythonint39'
    elif __sysversion_info.minor==10:
        __irispythonint = 'pythonint310'
    elif __sysversion_info.minor==11:
        __irispythonint = 'pythonint311'
    elif __sysversion_info.minor==12:
        __irispythonint = 'pythonint312'
    elif __sysversion_info.minor==13:
        __irispythonint = 'pythonint313'
else:
    __irispythonint = 'pythonint'

if __irispythonint is not None:
    # equivalent to from pythonint import *
    try:
        __irispythonintmodule = importlib.import_module(__irispythonint)
    except ImportError:
        __irispythonint = 'pythonint'
        __irispythonintmodule = importlib.import_module(__irispythonint)
    globals().update(vars(__irispythonintmodule))

# restore working directory
os.chdir(__ospath)

# TODO: Figure out how to hide __syspath and __ospath from anyone that
#       imports iris.  Tried __all__ but that only applies to this:
#           from iris import *

#
# End-of-file
#
