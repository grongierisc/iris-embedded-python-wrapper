import iris
import importlib
import os
import logging
from io import StringIO

def test_import_iris():
    import iris

    assert True

def test_import_iris_without_install_dir():
    os.environ.pop('IRISINSTALLDIR', None)
    os.environ.pop('ISC_PACKAGE_INSTALLDIR', None)

    try:
        importlib.reload(iris)
    except EnvironmentError:
        assert True
    else:
        assert False

def test_import_iris_without_credentials():
    import os
    os.environ.pop('IRISUSERNAME', None)

    # caputre logging output
    log_capture_string = StringIO()
    ch = logging.StreamHandler(log_capture_string)
    logging.getLogger().addHandler(ch)

    import iris

    assert "Embedded Python not available" in log_capture_string.getvalue()

