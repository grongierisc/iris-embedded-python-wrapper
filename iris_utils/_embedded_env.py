import importlib
import os
import sys
from typing import Optional


def get_install_dir_from_env() -> Optional[str]:
    return os.environ.get('IRISINSTALLDIR') or os.environ.get('ISC_PACKAGE_INSTALLDIR')


def is_embedded_kernel() -> bool:
    if bool(getattr(sys, "_embedded", 0)):
        return True

    public_iris = sys.modules.get('iris')
    if public_iris is None or getattr(public_iris, "__file__", None) is not None:
        return False

    return callable(getattr(public_iris, "__dict__", {}).get("cls"))


def get_preloaded_iris_kernel_module():
    public_iris = sys.modules.get('iris')
    if public_iris is None or getattr(public_iris, "__file__", None) is not None:
        return None
    if callable(getattr(public_iris, "__dict__", {}).get("cls")):
        return public_iris
    return None


def get_pythonint_module_name(version_info=None, os_name=None):
    version_info = version_info or sys.version_info
    os_name = os_name or os.name

    if os_name == 'nt':
        windows_modules = {
            9: 'pythonint39',
            10: 'pythonint310',
            11: 'pythonint311',
            12: 'pythonint312',
            13: 'pythonint313',
            14: 'pythonint314',
        }
        return windows_modules.get(version_info.minor)

    return 'pythonint'


def can_import_embedded_python(module_name: Optional[str] = None) -> bool:
    if module_name is None:
        module_name = get_pythonint_module_name()
    if module_name is None:
        return False
    try:
        importlib.import_module(module_name)
        return True
    except ImportError:
        return False
