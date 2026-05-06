import importlib
import os
import sys
from dataclasses import dataclass
from typing import Any, Literal, Optional

RuntimeMode = Literal['auto', 'embedded', 'native']
RuntimeState = Literal['embedded-kernel', 'embedded-local', 'native-remote', 'unavailable']
_UNSET = object()
_DLL_DIRECTORY_HANDLES = []
_DLL_DIRECTORY_PATHS = set()


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
    embedded_module: Any = None
    embedded_cls: Any = None
    embedded_connect: Any = None
    iris: Any = None
    dbapi: Any = None
    native_connection: Any = None
    native_connect: Any = None
    native_dbapi_module: Any = None

    def refresh(self) -> 'RuntimeContext':
        if not self.install_dir_explicit:
            self.install_dir = get_install_dir()
        if is_embedded_kernel():
            self.embedded_available = True
            self.state = 'embedded-kernel'
        elif (
            self.embedded_module is not None
            or self.embedded_cls is not None
            or self.embedded_connect is not None
        ):
            self.embedded_available = True
            self.state = 'embedded-local'
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
    def embedded_module(self) -> Any:
        return self._context.embedded_module

    @property
    def embedded_cls(self) -> Any:
        return self._context.embedded_cls

    @property
    def embedded_connect(self) -> Any:
        return self._context.embedded_connect

    @property
    def iris(self) -> Any:
        return self._context.iris

    @property
    def dbapi(self) -> Any:
        return self._context.dbapi

    @property
    def native_connection(self) -> Any:
        return self._context.native_connection

    @property
    def native_connect(self) -> Any:
        return self._context.native_connect

    @property
    def native_dbapi_module(self) -> Any:
        return self._context.native_dbapi_module

    def get(self) -> RuntimeContext:
        return self._context.refresh()

    def peek(self) -> RuntimeContext:
        return self._context

    def bind_backends(
        self,
        *,
        embedded_module: Any = _UNSET,
        embedded_cls: Any = _UNSET,
        embedded_connect: Any = _UNSET,
        native_connect: Any = _UNSET,
        native_dbapi_module: Any = _UNSET,
    ) -> RuntimeContext:
        embedded_updated = (
            embedded_module is not _UNSET
            or embedded_cls is not _UNSET
            or embedded_connect is not _UNSET
        )
        if embedded_module is not _UNSET:
            self._context.embedded_module = embedded_module
        if embedded_cls is not _UNSET:
            self._context.embedded_cls = embedded_cls
        if embedded_connect is not _UNSET:
            self._context.embedded_connect = embedded_connect
        if native_connect is not _UNSET:
            self._context.native_connect = native_connect
        if native_dbapi_module is not _UNSET:
            self._context.native_dbapi_module = native_dbapi_module
        return self._context.refresh() if embedded_updated else self._context

    def configure(
        self,
        mode: RuntimeMode = 'auto',
        install_dir: Optional[str] = _UNSET,
        iris: Any = _UNSET,
        dbapi: Any = _UNSET,
        native_connection: Any = _UNSET,
    ) -> RuntimeContext:
        self._context.mode = mode
        if install_dir is not _UNSET:
            self._context.install_dir = install_dir
            self._context.install_dir_explicit = True
            if install_dir is None:
                self._context.embedded_module = None
                self._context.embedded_cls = None
                self._context.embedded_connect = None
        # Treat configure() as setting the full runtime binding state.
        # Unspecified handles must be cleared to avoid stale native bindings
        # leaking into later embedded/auto configurations.
        self._context.iris = None if iris is _UNSET else iris
        self._context.dbapi = None if dbapi is _UNSET else dbapi
        self._context.native_connection = (
            None if native_connection is _UNSET else native_connection
        )
        return self._context.refresh()

    def reset(self) -> RuntimeContext:
        native_connect = self._context.native_connect
        native_dbapi_module = self._context.native_dbapi_module
        self._context = RuntimeContext().refresh()
        self._context.native_connect = native_connect
        self._context.native_dbapi_module = native_dbapi_module
        self._context.refresh()
        return self._context


runtime = RuntimeManager()


def update_dynalib_path(dynalib_path):
    # Determine the environment variable based on the operating system
    env_var = 'PATH'
    if sys.platform.startswith('win'):
        add_dll_directory = getattr(os, 'add_dll_directory', None)
        if add_dll_directory is not None:
            dll_path_key = os.path.normcase(os.path.abspath(dynalib_path))
            if dll_path_key not in _DLL_DIRECTORY_PATHS:
                try:
                    _DLL_DIRECTORY_HANDLES.append(add_dll_directory(dynalib_path))
                    _DLL_DIRECTORY_PATHS.add(dll_path_key)
                except OSError:
                    pass
    else:
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
    new_paths = (
        f"{current_paths}{os.pathsep}{dynalib_path}"
        if current_paths
        else dynalib_path
    )
    
    # Update the environment variable
    os.environ[env_var] = new_paths
