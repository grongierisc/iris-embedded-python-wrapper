from __future__ import print_function, absolute_import

# Standard library imports
import os
import sys
import shutil
import hashlib
import logging
import argparse
import functools
import sysconfig
import ctypes.util

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

is_windows = os.name == "nt"
is_apple = sys.platform == "darwin"

SHLIB_SUFFIX = sysconfig.get_config_var("SHLIB_SUFFIX")
if SHLIB_SUFFIX is None:
    if is_windows:
        SHLIB_SUFFIX = ".dll"
    else:
        SHLIB_SUFFIX = ".so"
if is_apple:
    # sysconfig.get_config_var("SHLIB_SUFFIX") can be ".so" in macOS.
    # Let's not use the value from sysconfig.
    SHLIB_SUFFIX = ".dylib"


def linked_libpython():
    """
    Find the linked libpython using dladdr (in *nix).

    Calling this in Windows always return `None` at the moment.

    Returns
    -------
    path : str or None
        A path to linked libpython.  Return `None` if statically linked.
    """
    if is_windows:
        return None
    return _linked_libpython_unix()


class Dl_info(ctypes.Structure):
    _fields_ = [
        ("dli_fname", ctypes.c_char_p),
        ("dli_fbase", ctypes.c_void_p),
        ("dli_sname", ctypes.c_char_p),
        ("dli_saddr", ctypes.c_void_p),
    ]


def _linked_libpython_unix():
    libdl = ctypes.CDLL(ctypes.util.find_library("dl"))
    libdl.dladdr.argtypes = [ctypes.c_void_p, ctypes.POINTER(Dl_info)]
    libdl.dladdr.restype = ctypes.c_int

    dlinfo = Dl_info()
    retcode = libdl.dladdr(
        ctypes.cast(ctypes.pythonapi.Py_GetVersion, ctypes.c_void_p),
        ctypes.pointer(dlinfo))
    if retcode == 0:  # means error
        return None
    path = os.path.realpath(dlinfo.dli_fname.decode())
    if path == os.path.realpath(sys.executable):
        return None
    return path


def library_name(name, suffix=SHLIB_SUFFIX, is_windows=is_windows):
    """
    Convert a file basename `name` to a library name (no "lib" and ".so" etc.)

    >>> library_name("libpython3.7m.so")                   # doctest: +SKIP
    'python3.7m'
    >>> library_name("libpython3.7m.so", suffix=".so", is_windows=False)
    'python3.7m'
    >>> library_name("libpython3.7m.dylib", suffix=".dylib", is_windows=False)
    'python3.7m'
    >>> library_name("python37.dll", suffix=".dll", is_windows=True)
    'python37'
    """
    if not is_windows and name.startswith("lib"):
        name = name[len("lib"):]
    if suffix and name.endswith(suffix):
        name = name[:-len(suffix)]
    return name


def append_truthy(list, item):
    if item:
        list.append(item)


def uniquifying(items):
    """
    Yield items while excluding the duplicates and preserving the order.

    >>> list(uniquifying([1, 2, 1, 2, 3]))
    [1, 2, 3]
    """
    seen = set()
    for x in items:
        if x not in seen:
            yield x
        seen.add(x)


def uniquified(func):
    """ Wrap iterator returned from `func` by `uniquifying`. """
    @functools.wraps(func)
    def wrapper(*args, **kwds):
        return uniquifying(func(*args, **kwds))
    return wrapper


@uniquified
def candidate_names(suffix=SHLIB_SUFFIX):
    """
    Iterate over candidate file names of libpython.

    Yields
    ------
    name : str
        Candidate name libpython.
    """
    LDLIBRARY = sysconfig.get_config_var("LDLIBRARY")
    if LDLIBRARY:
        yield LDLIBRARY

    LIBRARY = sysconfig.get_config_var("LIBRARY")
    if LIBRARY:
        yield os.path.splitext(LIBRARY)[0] + suffix

    dlprefix = "" if is_windows else "lib"
    sysdata = dict(
        v=sys.version_info,
        # VERSION is X.Y in Linux/macOS and XY in Windows:
        VERSION=(sysconfig.get_config_var("VERSION") or
                 "{v.major}.{v.minor}".format(v=sys.version_info)),
        ABIFLAGS=(sysconfig.get_config_var("ABIFLAGS") or
                  sysconfig.get_config_var("abiflags") or ""),
    )

    for stem in [
            "python{VERSION}{ABIFLAGS}".format(**sysdata),
            "python{VERSION}".format(**sysdata),
            "python{v.major}".format(**sysdata),
            "python",
            ]:
        yield dlprefix + stem + suffix



@uniquified
def candidate_paths(suffix=SHLIB_SUFFIX):
    """
    Iterate over candidate paths of libpython.

    Yields
    ------
    path : str or None
        Candidate path to libpython.  The path may not be a fullpath
        and may not exist.
    """

    yield linked_libpython()

    # List candidates for directories in which libpython may exist
    lib_dirs = []
    append_truthy(lib_dirs, sysconfig.get_config_var('LIBPL'))
    append_truthy(lib_dirs, sysconfig.get_config_var('srcdir'))
    append_truthy(lib_dirs, sysconfig.get_config_var("LIBDIR"))

    # LIBPL seems to be the right config_var to use.  It is the one
    # used in python-config when shared library is not enabled:
    # https://github.com/python/cpython/blob/v3.7.0/Misc/python-config.in#L55-L57
    #
    # But we try other places just in case.

    if is_windows:
        lib_dirs.append(os.path.join(os.path.dirname(sys.executable)))
    else:
        lib_dirs.append(os.path.join(
            os.path.dirname(os.path.dirname(sys.executable)),
            "lib"))

    # For macOS:
    append_truthy(lib_dirs, sysconfig.get_config_var("PYTHONFRAMEWORKPREFIX"))

    lib_dirs.append(sys.exec_prefix)
    lib_dirs.append(os.path.join(sys.exec_prefix, "lib"))

    lib_basenames = list(candidate_names(suffix=suffix))

    for directory in lib_dirs:
        for basename in lib_basenames:
            yield os.path.join(directory, basename)

    # In macOS and Windows, ctypes.util.find_library returns a full path:
    for basename in lib_basenames:
        yield ctypes.util.find_library(library_name(basename))

# Possibly useful links:
# * https://packages.ubuntu.com/bionic/amd64/libpython3.6/filelist
# * https://github.com/Valloric/ycmd/issues/518
# * https://github.com/Valloric/ycmd/pull/519


def normalize_path(path, suffix=SHLIB_SUFFIX, is_apple=is_apple):
    """
    Normalize shared library `path` to a real path.

    If `path` is not a full path, `None` is returned.  If `path` does
    not exists, append `SHLIB_SUFFIX` and check if it exists.
    Finally, the path is canonicalized by following the symlinks.

    Parameters
    ----------
    path : str ot None
        A candidate path to a shared library.
    """
    if not path:
        return None
    if not os.path.isabs(path):
        return None
    if os.path.exists(path):
        return os.path.realpath(path)
    if os.path.exists(path + suffix):
        return os.path.realpath(path + suffix)
    if is_apple:
        return normalize_path(_remove_suffix_apple(path),
                              suffix=".so", is_apple=False)
    return None


def _remove_suffix_apple(path):
    """
    Strip off .so or .dylib.

    >>> _remove_suffix_apple("libpython.so")
    'libpython'
    >>> _remove_suffix_apple("libpython.dylib")
    'libpython'
    >>> _remove_suffix_apple("libpython3.7")
    'libpython3.7'
    """
    if path.endswith(".dylib"):
        return path[:-len(".dylib")]
    if path.endswith(".so"):
        return path[:-len(".so")]
    return path


@uniquified
def finding_libpython():
    """
    Iterate over existing libpython paths.

    The first item is likely to be the best one.

    Yields
    ------
    path : str
        Existing path to a libpython.
    """
    logger.debug("is_windows = %s", is_windows)
    logger.debug("is_apple = %s", is_apple)
    for path in candidate_paths():
        logger.debug("Candidate: %s", path)
        normalized = normalize_path(path)
        if normalized:
            logger.debug("Found: %s", normalized)
            yield normalized
        else:
            logger.debug("Not found.")


def find_libpython():
    """
    Return a path (`str`) to libpython or `None` if not found.

    Parameters
    ----------
    path : str or None
        Existing path to the (supposedly) correct libpython.
    """
    for path in finding_libpython():
        return os.path.realpath(path)
    

def _write_cpf_content(filename, lines):
    """Helper function to write CPF file content"""
    with open(filename, "w") as f:
        f.writelines(lines)
    
def _get_config_section(lines):
    """Find or create config section in CPF file"""
    config_section = next((i for i, line in enumerate(lines) 
                            if "[config]" in line.lower()), None)
    if config_section is None:
        lines.append("[config]\n")
        config_section = len(lines) - 1
    return config_section

def _get_python_config(libpython, path, libpythonversion=sys.version[:4]):
    """Get Python configuration lines"""
    return {
        'runtime': f"PythonRuntimeLibrary={libpython}\n",
        'path': f"PythonPath={path}\n", 
        'version': f"PythonRuntimeLibraryVersion={libpythonversion}\n"
    }

def _update_existing_config(lines, config_section, config):
    """Update existing configuration section"""
    config_keys = {}
    for i, line in enumerate(lines[config_section:]):
        if line.startswith("PythonRuntimeLibrary="):
            config_keys['runtime'] = i + config_section
        elif line.startswith("PythonPath="):
            config_keys['path'] = i + config_section
        elif line.startswith("PythonRuntimeLibraryVersion="):
            config_keys['version'] = i + config_section

    # Validate required keys
    required_keys = ['runtime', 'path'] 
    missing = [k for k in required_keys if k not in config_keys]
    if missing:
        raise RuntimeError(f"Missing required keys: {', '.join(missing)}")

    # Update values
    lines[config_keys['runtime']] = config['runtime']
    lines[config_keys['path']] = config['path']
    if 'version' in config_keys:
        lines[config_keys['version']] = config['version']

def update_iris_cpf(libpython, path):
    """Update main IRIS CPF file"""
    installdir = _find_iris_install_dir()

    iris_cpf = os.path.join(installdir, "iris.cpf")
    if not os.path.exists(iris_cpf):
        raise RuntimeError(f"Configuration file not found: {iris_cpf}")

    try:
        with open(iris_cpf, "r") as f:
            lines = f.readlines()

        config_section = _get_config_section(lines)
        config = _get_python_config(libpython, path)
        _update_existing_config(lines, config_section, config)
        _write_cpf_content(iris_cpf, lines)

        logger.info("Successfully updated iris.cpf configuration")
        log_config_changes(libpython, path)
        logger.warning("Please restart IRIS instance to apply changes")

    except Exception as e:
        logger.error(f"Failed to update iris.cpf: {str(e)}")
        raise

def update_merge_iris_cpf(libpython, path, libpythonversion=sys.version[:4]):
    """Update merge CPF file"""
    merge_cpf_file = os.environ.get('ISC_CPF_MERGE_FILE')
    if not merge_cpf_file:
        return _create_new_merge_file(libpython, path)

    try:
        with open(merge_cpf_file, "r") as f:
            lines = f.readlines()

        config_section = _get_config_section(lines)
        config = _get_python_config(libpython, path, libpythonversion)
        
        if config_section == len(lines) - 1:  # New section was added
            lines.extend([config['runtime'], config['path'], config['version']])
        else:
            _update_existing_config(lines, config_section, config)
            
        _write_cpf_content(merge_cpf_file, lines)
        logger.info(f"Successfully updated {merge_cpf_file}")
        log_config_changes(libpython, path)

    except Exception as e:
        logger.error(f"Failed to update merge file: {str(e)}")
        raise

def _create_new_merge_file(libpython, path):
    """Create new merge CPF file"""
    installdir = _find_iris_install_dir()

    iris_cpf = os.path.join(installdir, "iris_python_merge.cpf")
    config = _get_python_config(libpython, path)

    try:
        with open(iris_cpf, "w") as f:
            f.write("[config]\n")
            f.writelines([config['runtime'], config['path'], config['version']])

        iris_instance = find_iris_instance(installdir)
        if iris_instance:
            os.system(f"iris merge {iris_instance} {iris_cpf}")
            logger.info(f"Successfully merged with instance: {iris_instance}")
            log_config_changes(libpython, path)
        else:
            logger.error("Failed to find IRIS instance")

    except Exception as e:
        logger.error(f"Failed to create merge file: {str(e)}")
        raise

def _find_iris_install_dir():
    """Find IRIS installation directory"""
    installdir = os.environ.get('IRISINSTALLDIR') or os.environ.get('ISC_PACKAGE_INSTALLDIR')
    if not installdir:
        raise EnvironmentError("IRISINSTALLDIR environment variable must be set")
    return installdir

def _make_a_backup(iris_cpf, path):
    """Create a backup of iris.cpf file"""
    backup_suffix = hashlib.md5(path.encode()).hexdigest()
    backup_file = f"{iris_cpf}.{backup_suffix}"
    shutil.copy2(iris_cpf, backup_file)
    logger.info(f"Created backup at {backup_file}")
    return backup_file

def find_iris_instance(installdir):
    """Find IRIS instance from iris all command"""
    iris_all = os.popen("iris all").read()
    for line in iris_all.split("\n"):
        if installdir in line:
            return line.split(">")[1].split()[0]
    return None

def bind():
    parser = argparse.ArgumentParser()
    parser.add_argument("--namespace", default="")
    args = parser.parse_args()

    libpython = find_libpython()
    if not libpython:
        raise RuntimeError("libpython not found")
    
    path = _get_path()

    installdir = _find_iris_install_dir()
    iris_cpf = os.path.join(installdir, "iris.cpf")
    _make_a_backup(iris_cpf, path)

    if is_windows:
        update_iris_cpf(libpython, path)
    else:
        update_merge_iris_cpf(libpython, path)

def unbind():
    backup_file = _get_backup_file(_get_path())
    iris_cpf = os.path.join(_find_iris_install_dir(), "iris.cpf")
    if is_windows:
        if backup_file:
            shutil.copy2(backup_file, iris_cpf)
            logger.info("Successfully restored iris.cpf from backup")
            logger.warning("Please restart IRIS instance to apply changes")
        else:
            logger.warning("Backup file not found")
    else:
        libpython = path = libpythonversion = ""
        if backup_file:
            with open(backup_file, "r") as f:
                lines = f.readlines()
            config_section = _get_config_section(lines)

            libpython = next((line for line in lines[config_section:] if line.startswith("PythonRuntimeLibrary=")), None)
            path = next((line for line in lines[config_section:] if line.startswith("PythonPath=")), None)
            libpythonversion = next((line for line in lines[config_section:] if line.startswith("PythonRuntimeLibraryVersion=")), None)
        else:
            logger.warning("Backup file not found, using default values")

        update_merge_iris_cpf(libpython, path, libpythonversion)

def _get_path():
    path = ""
    if "VIRTUAL_ENV" in os.environ:
        path = os.path.join(os.environ["VIRTUAL_ENV"], "lib", f"python{sys.version[:4]}", "site-packages")
    return path

def _get_backup_file(path):
    """Find the backup file"""
    iris_cpf = os.path.join(_find_iris_install_dir(), "iris.cpf")
    backup_suffix = hashlib.md5(path.encode()).hexdigest()
    backup_file = f"{iris_cpf}.{backup_suffix}"
    return backup_file if os.path.exists(backup_file) else None

def log_config_changes(libpython, path):
    """Log configuration changes"""
    logger.info("PythonRuntimeLibrary path set to %s", libpython)
    logger.info("PythonPath set to %s", path)
