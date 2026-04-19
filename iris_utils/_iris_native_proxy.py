import logging

def wrap_result(res, db):
    """
    Wraps the result from Native API if it is an IRISObject.
    Automatically unwraps streams and dynamic objects into Python primitives.
    """
    if res.__class__.__name__ == 'IRISObject':
        # 1. Identify the IRIS Class Name
        try:
            classname = res.invoke("%ClassName", 1)
        except Exception:
            classname = ""

        # 2. Automatically deserialize %DynamicObject and %DynamicArray to dict/list
        if classname in ("%Library.DynamicObject", "%Library.DynamicArray"):
            import json
            try:
                # Dump JSON to a temporary stream to read it back natively
                s = db.classMethodValue("%Stream.GlobalCharacter", "%New")
                
                res.invoke("%ToJSON", s)
                s.invoke("Rewind")
                size = s.get("Size")
                content = s.invoke("Read", size) if size and size > 0 else ""
                
                return json.loads(content)
            except Exception:
                pass # Fallback to proxy if it fails

        # 3. Automatically deserialize Streams to bytes/str
        elif classname in ("%Stream.GlobalBinary", "%Stream.GlobalCharacter", "%Stream.FileBinary", "%Stream.FileCharacter"):
            try:
                res.invoke("Rewind")
                size = res.get("Size")
                if not size: return b"" if "Binary" in classname else ""
                content = res.invoke("Read", size)
                
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
            res = self._db.classMethodValue(self._class_name, mapped_name, *_wrap_args(args, self._db))
            return wrap_result(res, self._db)

        return method_proxy

_CLASS_PROPERTIES_CACHE = {}

def _get_class_properties(classname, db):
    if classname in _CLASS_PROPERTIES_CACHE:
        return _CLASS_PROPERTIES_CACHE[classname]
        
    props = set()
    try:
        sql = "SELECT Name FROM %Dictionary.CompiledProperty WHERE parent = ?"
        rs = db.classMethodObject("%SQL.Statement", "%ExecDirect", None, sql, classname)
        while rs.invoke("%Next"):
            name = rs.get("Name")
            props.add(name)
    except Exception:
        pass
        
    _CLASS_PROPERTIES_CACHE[classname] = props
    return props

class NativeObjectProxy:
    def __init__(self, oref, db):
        self._oref = oref
        self._db = db
        try:
            self._iris_classname = oref.invoke("%ClassName", 1)
        except Exception:
            self._iris_classname = ""

    def __getattr__(self, name):
        # FIX: Don't proxy standard Python internal lookups to IRIS
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")

        mapped_name = name.replace("_", "%", 1) if name.startswith("_") else name
        
        props = _get_class_properties(self._iris_classname, self._db)
        if mapped_name in props:
            val = self._oref.get(mapped_name)
            return wrap_result(val, self._db)
        else:
            def method_proxy(*args):
                res = self._oref.invoke(mapped_name, *_wrap_args(args, self._db))
                return wrap_result(res, self._db)
            return method_proxy

    def __setattr__(self, name, value):
        if name in ["_oref", "_db", "_iris_classname"]:
            super().__setattr__(name, value)
            return
        
        # FIX: Unwrap proxy payload before sending to IRIS
        if isinstance(value, NativeObjectProxy):
            value = value._oref
        
        mapped_name = name.replace("_", "%", 1) if name.startswith("_") else name
        self._oref.set(mapped_name, value)
