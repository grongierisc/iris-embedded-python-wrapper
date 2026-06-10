import logging as _logging
import os as _os

_logging.getLogger(__name__).addHandler(_logging.NullHandler())

from . import _bootstrap
from . import iris_ipm
from ._byref import ByRef, make_ref
from ._list import IRISList
from ._vector import IRISVector, Vector
from .iris_ipm import ipm
from ._runtime_facade import initialize_module as _initialize_module

__ospath = _os.getcwd()
try:
    _facade = _initialize_module(globals(), __name__)
finally:
    _os.chdir(__ospath)
