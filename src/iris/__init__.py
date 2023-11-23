from sys import path as __syspath
import os
from .iris_ipm import ipm

# check for install dir in environment
# environment to check is IRISINSTALLDIR
# if not found, raise exception and exit
# ISC_PACKAGE_INSTALLDIR - defined by default in Docker images
installdir = os.environ.get('IRISINSTALLDIR') or os.environ.get('ISC_PACKAGE_INSTALLDIR')
if installdir is None:
        raise Exception("""Cannot find InterSystems IRIS installation directory
    Please set IRISINSTALLDIR environment variable to the InterSystems IRIS installation directory""")

# join the install dir with the bin directory
__syspath.append(os.path.join(installdir, 'bin'))
# also append lib/python
__syspath.append(os.path.join(installdir, 'lib', 'python'))

# save working directory
__ospath = os.getcwd()

from pythonint import *

# restore working directory
os.chdir(__ospath)

# TODO: Figure out how to hide __syspath and __ospath from anyone that
#       imports iris.  Tried __all__ but that only applies to this:
#           from iris import *

#
# End-of-file
#
