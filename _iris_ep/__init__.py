import logging as _logging
import os as _os

_logging.basicConfig(level=_logging.INFO)

from . import _bootstrap
from . import iris_ipm
from .iris_ipm import ipm
from ._runtime_facade import initialize_module as _initialize_module

__ospath = _os.getcwd()
try:
    _facade = _initialize_module(globals(), __name__)
finally:
    _os.chdir(__ospath)
