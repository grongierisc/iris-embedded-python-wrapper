import importlib
import os
import sys

from iris_utils import update_dynalib_path


def get_install_dir_from_env():
    return os.environ.get('IRISINSTALLDIR') or os.environ.get('ISC_PACKAGE_INSTALLDIR')


def configure_install_dir(path):
    if not path:
        raise ValueError("path must be a non-empty IRIS installation directory")

    install_dir = os.path.abspath(os.fspath(path))
    bin_dir = os.path.join(install_dir, 'bin')
    python_dir = os.path.join(install_dir, 'lib', 'python')

    if bin_dir not in sys.path:
        sys.path.append(bin_dir)
    if python_dir not in sys.path:
        sys.path.append(python_dir)

    update_dynalib_path(bin_dir)
    return install_dir


def is_embedded_kernel():
    return bool(getattr(sys, "_embedded", 0))


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


def import_embedded_kernel_module():
    return importlib.import_module('irisep')


def import_pythonint_module(module_name=None):
    module_name = module_name or get_pythonint_module_name()
    if module_name is None:
        raise RuntimeError(
            f"Embedded Python is not available for Python {sys.version_info.major}.{sys.version_info.minor}"
        )

    try:
        return importlib.import_module(name=module_name)
    except ModuleNotFoundError:
        if module_name == 'pythonint':
            raise
        return importlib.import_module(name='pythonint')
