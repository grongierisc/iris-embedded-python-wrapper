import logging

def wrap_result(res, db):
    """
    Wraps the result from Native API if it is an IRISObject.
    Avoids explicit imports of intersystems_iris to keep dependencies optional.
    """
    # Check if the result is an instance of IRISObject by class name
    if res.__class__.__name__ == 'IRISObject':
        return NativeObjectProxy(res, db)
    return res

class NativeClassProxy:
    def __init__(self, class_name, db):
        self._class_name = class_name
        self._db = db

    def __getattr__(self, name):
        # Map `_` to `%` for the first character
        mapped_name = name.replace("_", "%", 1) if name.startswith("_") else name

        def method_proxy(*args):
            # Support both old API (invokeClassMethod) and new API (classMethodValue)
            if hasattr(self._db, 'invokeClassMethod'):
                res = self._db.invokeClassMethod(self._class_name, mapped_name, *args)
            else:
                res = self._db.classMethodValue(self._class_name, mapped_name, *args)
            return wrap_result(res, self._db)

        return method_proxy

class NativeObjectProxy:
    def __init__(self, oref, db):
        self._oref = oref
        self._db = db

    def __getattr__(self, name):
        # FIX: Don't proxy standard Python internal lookups to IRIS
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")

        mapped_name = name.replace("_", "%", 1) if name.startswith("_") else name
        
        # Speculative property read:
        # Since Native API does not tell us immediately if an attribute is a property or method,
        # we try fetching it as a property first.
        try:
            # New API: use oref.get(propName); Old API: use db.get(oref, propName)
            if hasattr(self._oref, 'get') and not hasattr(self._db, 'invokeClassMethod'):
                val = self._oref.get(mapped_name)
            else:
                val = self._db.get(self._oref, mapped_name)
            return wrap_result(val, self._db)
        except Exception as e:
            # If property access fails (likely it's a method or doesn't exist), return a method callable
            def method_proxy(*args):
                # New API: use oref.invoke(methodName, ...); Old API: use db.invoke(oref, ...)
                if hasattr(self._oref, 'invoke') and not hasattr(self._db, 'invokeClassMethod'):
                    res = self._oref.invoke(mapped_name, *args)
                else:
                    res = self._db.invoke(self._oref, mapped_name, *args)
                return wrap_result(res, self._db)
            return method_proxy

    def __setattr__(self, name, value):
        if name in ["_oref", "_db"]:
            super().__setattr__(name, value)
            return
        
        # FIX: Unwrap proxy payload before sending to IRIS
        if isinstance(value, NativeObjectProxy):
            value = value._oref
        
        mapped_name = name.replace("_", "%", 1) if name.startswith("_") else name
        if hasattr(self._oref, 'set') and not hasattr(self._db, 'invokeClassMethod'):
            self._oref.set(mapped_name, value)
        else:
            self._db.set(self._oref, mapped_name, value)
