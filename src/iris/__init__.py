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

def __getattr__(name):
    try:
        return globals()[name]
    except KeyError:
        return __get_iris_object__(name)
 
def __get_iris_object__(name:str):
    try:
        # replace '_' with '%'
        name = name.replace('_', '%')
        return cls(name)
    except RuntimeError:
        return __get_iris_package__(name)
 
def __get_iris_package__(name:str):
    return IrisPackage(name)
 
class IrisPackage:
    def __init__(self, name:str):
        self.name = name
 
    def __getattr__(self, name):
        try:
            return globals()[f"{self.name}.{name}"]
        except KeyError:
            return __get_iris_object__(f"{self.name}.{name}")