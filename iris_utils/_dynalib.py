import os
import sys

_DLL_DIRECTORY_HANDLES = []
_DLL_DIRECTORY_PATHS = set()


def update_dynalib_path(dynalib_path):
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
        env_var = 'PATH'
        current_paths = os.environ.get(env_var, '')
        new_paths = (
            f"{current_paths}{os.pathsep}{dynalib_path}"
            if current_paths
            else dynalib_path
        )
        os.environ[env_var] = new_paths
        return

    # LD_LIBRARY_PATH/DYLD_LIBRARY_PATH are read by the Unix dynamic loader
    # before process startup. Mutating them here is misleading and does not
    # repair dependency resolution for the current Python process.
    setdlopenflags = getattr(sys, "setdlopenflags", None)
    getdlopenflags = getattr(sys, "getdlopenflags", None)
    rtld_global = getattr(os, "RTLD_GLOBAL", 0)
    if callable(setdlopenflags) and callable(getdlopenflags) and rtld_global:
        setdlopenflags(getdlopenflags() | rtld_global)
