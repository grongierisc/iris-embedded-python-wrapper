import logging

def wrap_result(res, db):
    """
    Wraps the result from Native API if it is an IRISObject.
    Automatically unwraps streams and dynamic objects into Python primitives.
    """
    if res.__class__.__name__ == 'IRISObject':
        # 1. Identify the IRIS Class Name
        try:
            # Native API format: res.invoke() or db.invoke(res)
            if hasattr(res, 'invoke'):
                classname = res.invoke("%ClassName", 1)
            else:
                classname = db.invoke(res, "%ClassName", 1)
        except Exception:
            classname = ""

        # 2. Automatically deserialize %DynamicObject and %DynamicArray to dict/list
        if classname in ("%Library.DynamicObject", "%Library.DynamicArray"):
            import json
            try:
                # Dump JSON to a temporary stream to read it back natively
                if hasattr(db, 'classMethodValue'):
                    s = db.classMethodValue("%Stream.GlobalCharacter", "%New")
                else:
                    s = db.invokeClassMethod("%Stream.GlobalCharacter", "%New")
                
                if hasattr(res, 'invoke'):
                    res.invoke("%ToJSON", s)
                    s.invoke("Rewind")
                    size = s.get("Size")
                    content = s.invoke("Read", size) if size and size > 0 else ""
                else:
                    db.invoke(res, "%ToJSON", s)
                    db.invoke(s, "Rewind")
                    size = db.get(s, "Size")
                    content = db.invoke(s, "Read", size) if size and size > 0 else ""
                
                return json.loads(content)
            except Exception:
                pass # Fallback to proxy if it fails

        # 3. Automatically deserialize Streams to bytes/str
        elif classname in ("%Stream.GlobalBinary", "%Stream.GlobalCharacter", "%Stream.FileBinary", "%Stream.FileCharacter"):
            try:
                if hasattr(res, 'invoke'):
                    res.invoke("Rewind")
                    size = res.get("Size")
                    if not size: return b"" if "Binary" in classname else ""
                    content = res.invoke("Read", size)
                else:
                    db.invoke(res, "Rewind")
                    size = db.get(res, "Size")
                    if not size: return b"" if "Binary" in classname else ""
                    content = db.invoke(res, "Read", size)
                
                # Native API sometimes parses binary wire payload as strings, encode to bytes
                if "Binary" in classname and isinstance(content, str):
                    return content.encode('latin1')
                return content
            except Exception:
                pass # Fallback to proxy if it fails

        # 4. Fallback for all other IRIS objects
        return NativeObjectProxy(res, db)
        
    return res


def _wrap_args(args, db):
    new_args = []
    for value in args:
        if isinstance(value, NativeObjectProxy):
            new_args.append(value._oref)
        else:
            new_args.append(value)
    return new_args

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
                res = self._db.invokeClassMethod(self._class_name, mapped_name, *_wrap_args(args, self._db))
            else:
                res = self._db.classMethodValue(self._class_name, mapped_name, *_wrap_args(args, self._db))
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
                    res = self._oref.invoke(mapped_name, *_wrap_args(args, self._db))
                else:
                    res = self._db.invoke(self._oref, mapped_name, *_wrap_args(args, self._db))
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
