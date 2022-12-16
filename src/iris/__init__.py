from sys import path as __syspath
import os

# check for install dir in environment
# environment to check is IRISINSTALLDIR
# if not found, raise exception and exit
installdir = os.environ.get('IRISINSTALLDIR')
if installdir is None:
        raise Exception("""Cannot find InterSystems IRIS installation directory
    Please set IRISINSTALLDIR environment variable to the InterSystems IRIS installation directory""")

# join the install dir with the bin directory
# add this to the python path
__syspath.append(os.path.join(installdir, 'bin'))

from pythonint import *
import iris.irisloader
import iris.irisbuiltins

__syspath.remove(os.path.join(installdir, 'bin'))

# TODO: Figure out how to hide __syspath and __ospath from anyone that
#       imports iris.  Tried __all__ but that only applies to this:
#           from iris import *

#
# End-of-file
#
