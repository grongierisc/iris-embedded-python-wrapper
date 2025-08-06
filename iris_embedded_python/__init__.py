import os
import sys
import importlib
import logging

logging.basicConfig(level=logging.INFO)

from .iris_ipm import ipm
from .iris_utils import update_dynalib_path

# check for install dir in environment
# environment to check is IRISINSTALLDIR
# if not found, raise exception and exit
# ISC_PACKAGE_INSTALLDIR - defined by default in Docker images
installdir = os.environ.get('IRISINSTALLDIR') or os.environ.get('ISC_PACKAGE_INSTALLDIR')
__sysversion_info = sys.version_info
__syspath = sys.path
__osname = os.name

if installdir is None:
    logging.warning("IRISINSTALLDIR or ISC_PACKAGE_INSTALLDIR environment variable must be set")
    logging.warning("Embedded Python not available")
else:
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
    try:
    # try to import the pythonint module
        try:
            __iris_module = importlib.import_module(name=__irispythonint)
        except ModuleNotFoundError:
            __irispythonint = 'pythonint'
            __iris_module = importlib.import_module(name=__irispythonint)
        globals().update(__iris_module.__dict__)
    except ImportError as e:
        logging.warning("Error importing %s: %s", __irispythonint, e)
        logging.warning("Embedded Python not available")
        def __getattr__(name):
            if name in ['cls', 'sql']:
                logging.warning(f"Class or module '{name}' not found in iris_embedded_python. Returning a mock object. Make sure you local installation is correct.")
                from unittest.mock import MagicMock
                return MagicMock()
            else:
                return []
    

# restore working directory
os.chdir(__ospath)

