from __future__ import print_function, absolute_import

import os
import shutil
import sys
import argparse
import logging
logging.basicConfig(level=logging.INFO)

import hashlib

import ctypes.util
import functools
import sysconfig

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

def update_iris_cpf(libpython, path):
    
    # try to find the iris.cpf file
    installdir = os.environ.get('IRISINSTALLDIR') or os.environ.get('ISC_PACKAGE_INSTALLDIR')
    if installdir is None:
            raise EnvironmentError("""Cannot find InterSystems IRIS installation directory
        Please set IRISINSTALLDIR environment variable to the InterSystems IRIS installation directory""")
    iris_cpf = os.path.join(installdir, "iris.cpf")

    if not os.path.exists(iris_cpf):
        logging.error("iris.cpf not found")
        raise RuntimeError("iris.cpf not found")
    
    # open iris.cpf it's an ini file
    with open(iris_cpf, "r") as f:
        lines = f.readlines()

    # find the [config] section
    config_section = None

    for i, line in enumerate(lines):
        if "[config]" in line:
            config_section = i
            break

    if config_section is None:
        logging.error("[config] section not found")
        raise RuntimeError("[config] section not found")
    
    # find the PythonRuntimeLibrary and PythonPath keys
    python_runtime_library = None
    python_path = None
    python_runtime_library_version = None

    for i, line in enumerate(lines[config_section:]):
        if "PythonRuntimeLibrary" in line and python_runtime_library is not None:
            python_runtime_library = i + config_section
        if "PythonPath" in line and python_path is not None:
            python_path = i + config_section
        if "PythonRuntimeLibraryVersion" in line and python_runtime_library_version is not None:
            python_runtime_library_version = i + config_section

    if python_runtime_library is None:
        logging.error("PythonRuntimeLibrary key not found")
        raise RuntimeError("PythonRuntimeLibrary key not found")
    
    if python_path is None:
        logging.error("PythonPath key not found")
        raise RuntimeError("PythonPath key not found")
    
    # backup the current values by copying the iris.cpf file
    iris_cpf_backup = iris_cpf + hashlib.md5(path.encode()).hexdigest()
    shutil.copy(iris_cpf, iris_cpf_backup)

    # update the values
    lines[python_runtime_library] = f"PythonRuntimeLibrary={libpython}\n"
    lines[python_path] = f"PythonPath={path}\n"
    if python_runtime_library_version is not None:
        lines[python_runtime_library_version] = f"PythonRuntimeLibraryVersion={sys.version[:4]}\n"

    # write the changes back to the iris.cpf file
    with open(iris_cpf, "w") as f:
        f.writelines(lines)


def bind():
    parser = argparse.ArgumentParser()
    parser.add_argument("--namespace", default="")
    args = parser.parse_args()

    path = ""

    libpython = find_libpython()
    if not libpython:
        logging.error("libpython not found")
        raise RuntimeError("libpython not found")
    
    # Set the new libpython path
    if "VIRTUAL_ENV" in os.environ:
        # we are not in a virtual environment
        path = os.path.join(os.environ["VIRTUAL_ENV"], "lib", "python" + sys.version[:4], "site-packages")

    update_iris_cpf(libpython, path)

    log_config_changes(libpython, path)

def unbind():

    # try to find the iris.cpf file
    installdir = os.environ.get('IRISINSTALLDIR') or os.environ.get('ISC_PACKAGE_INSTALLDIR')
    if installdir is None:
            raise EnvironmentError("""Cannot find InterSystems IRIS installation directory
        Please set IRISINSTALLDIR environment variable to the InterSystems IRIS installation directory""")
    iris_cpf = os.path.join(installdir, "iris.cpf")

    if not os.path.exists(iris_cpf):
        logging.error("iris.cpf not found")
        raise RuntimeError("iris.cpf not found")
    
    libpython = ""
    path = ""
    # Set the new libpython path
    if "VIRTUAL_ENV" in os.environ:
        # we are not in a virtual environment
        path = os.path.join(os.environ["VIRTUAL_ENV"], "lib", "python" + sys.version[:4], "site-packages")

    # try to find the backup file
    iris_cpf_backup = iris_cpf + hashlib.md5(path.encode()).hexdigest()

    if not os.path.exists(iris_cpf_backup):
        # update the current cpf file with the default values
        update_iris_cpf(libpython, path)
    else:
        # restore the backup
        shutil.copy(iris_cpf_backup, iris_cpf)
        os.remove(iris_cpf_backup)

    log_config_changes(libpython, path)

def log_config_changes(libpython, path):
    logging.info("PythonRuntimeLibrary path set to %s", libpython)
    logging.info("PythonPath set to %s", path)
