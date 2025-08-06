from iris_embedded_python import *
try:
    from iris_embedded_python import __getattr__
except ImportError:
    def __getattr__(name):
        if name in ['cls', 'sql']:
            logging.warning(f"Class or module '{name}' not found in iris_embedded_python. Returning a mock object. Make sure you local installation is correct.")
            from unittest.mock import MagicMock
            return MagicMock()
        else:
            return []
