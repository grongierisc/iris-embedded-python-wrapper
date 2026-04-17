import importlib
import os
import sys
from dataclasses import dataclass
from typing import Any, Literal, Optional

RuntimeMode = Literal['auto', 'embedded', 'native']
RuntimeState = Literal['embedded-kernel', 'embedded-local', 'native-remote', 'unavailable']
_UNSET = object()


def get_install_dir() -> Optional[str]:
    return os.environ.get('IRISINSTALLDIR') or os.environ.get('ISC_PACKAGE_INSTALLDIR')


def is_embedded_kernel() -> bool:
    return bool(getattr(sys, '_embedded', 0))


def get_pythonint_module_name(version_info: Optional[sys.version_info] = None, os_name: Optional[str] = None) -> Optional[str]:
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


@dataclass
class RuntimeContext:
    mode: RuntimeMode = 'auto'
    state: RuntimeState = 'unavailable'
    install_dir: Optional[str] = None
    install_dir_explicit: bool = False
    embedded_available: bool = False
    iris: Any = None
    dbapi: Any = None
    native_connection: Any = None

    def refresh(self) -> 'RuntimeContext':
        if not self.install_dir_explicit:
            self.install_dir = get_install_dir()
        if is_embedded_kernel():
            self.embedded_available = True
            self.state = 'embedded-kernel'
        elif self.install_dir and can_import_embedded_python():
            self.embedded_available = True
            self.state = 'embedded-local'
        elif self.iris is not None or self.dbapi is not None or self.native_connection is not None:
            self.embedded_available = False
            self.state = 'native-remote'
        else:
            self.embedded_available = False
            self.state = 'unavailable'
        return self


class RuntimeManager:
    def __init__(self):
        self._context = RuntimeContext().refresh()

    @property
    def mode(self) -> RuntimeMode:
        return self._context.mode

    @property
    def state(self) -> RuntimeState:
        return self._context.state

    @property
    def embedded_available(self) -> bool:
        return self._context.embedded_available

    @property
    def iris(self) -> Any:
        return self._context.iris

    @property
    def dbapi(self) -> Any:
        return self._context.dbapi

    @property
    def native_connection(self) -> Any:
        return self._context.native_connection

    def get(self) -> RuntimeContext:
        return self._context.refresh()

    def configure(
        self,
        mode: RuntimeMode = 'auto',
        install_dir: Optional[str] = _UNSET,
        iris: Any = None,
        dbapi: Any = None,
        native_connection: Any = None,
    ) -> RuntimeContext:
        self._context.mode = mode
        if install_dir is not _UNSET:
            self._context.install_dir = install_dir
            self._context.install_dir_explicit = True
        if iris is not None or mode == 'native':
            self._context.iris = iris
        if dbapi is not None:
            self._context.dbapi = dbapi
        if native_connection is not None:
            self._context.native_connection = native_connection
        return self._context.refresh()

    def reset(self) -> RuntimeContext:
        self._context = RuntimeContext().refresh()
        return self._context


runtime = RuntimeManager()


def update_dynalib_path(dynalib_path):
    # Determine the environment variable based on the operating system
    env_var = 'PATH'
    if not sys.platform.startswith('win'):
        # set flags to allow dynamic loading of shared libraries
        sys.setdlopenflags(sys.getdlopenflags() | os.RTLD_GLOBAL)
        if sys.platform == 'darwin':
            env_var = 'DYLD_LIBRARY_PATH'
        else:
            env_var = 'LD_LIBRARY_PATH'
            
    # Get the current value of the environment variable
    current_paths = os.environ.get(env_var, '')
    
    # Update the environment variable by appending the dynalib path
    # Note: You can prepend instead by reversing the order in the join
    new_paths = f"{current_paths}:{dynalib_path}" if current_paths else dynalib_path
    
    # Update the environment variable
    os.environ[env_var] = new_paths

