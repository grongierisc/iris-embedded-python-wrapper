import sys
import os


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

