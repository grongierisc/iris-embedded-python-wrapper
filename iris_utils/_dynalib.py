import os
import sys

_DLL_DIRECTORY_HANDLES = []
_DLL_DIRECTORY_PATHS = set()


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
