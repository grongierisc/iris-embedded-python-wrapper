import logging

try:
    from _iris_ep._byref import ByRef
except Exception:  # pragma: no cover - iris_utils can be imported standalone.
    ByRef = None

try:
    from _iris_ep._vector import IRISVector
except Exception:  # pragma: no cover - iris_utils can be imported standalone.
    IRISVector = None


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


def _is_vector(value):
    return IRISVector is not None and isinstance(value, IRISVector)


def _wrap_value(value):
    if isinstance(value, NativeObjectProxy):
        return value._oref
    if _is_vector(value):
        return value.to_param()
    return value


def _wrap_args(args, db):
    return [_wrap_value(value) for value in args]


def _get_native_reference_class(db):
    module_names = []
    db_module = getattr(type(db), "__module__", "")
    if db_module:
        module_names.append(db_module.split(".", 1)[0])
    module_names.extend(("iris", "intersystems_iris"))

    for module_name in module_names:
        try:
            module = __import__(module_name)
            reference_cls = getattr(module, "IRISReference", None)
        except Exception:
            reference_cls = None
        if reference_cls is not None:
            return reference_cls

    return None


def _is_byref(value):
    return ByRef is not None and isinstance(value, ByRef)


def _make_native_reference(value, db):
    reference_cls = _get_native_reference_class(db)
    if reference_cls is None:
        return None

    native_value = _wrap_value(value.value)
    try:
        return reference_cls(native_value, value.type)
    except TypeError:
        return reference_cls(native_value)


def _read_native_reference(reference):
    for method_name in ("getValue", "get_value", "getObject"):
        method = getattr(reference, method_name, None)
        if callable(method):
            return method()
    return getattr(reference, "value")


def _wrap_args_with_refs(args, db):
    wrapped_args = []
    refs = []

    for value in args:
        if _is_byref(value):
            native_ref = _make_native_reference(value, db)
            if native_ref is None:
                wrapped_args.append(_wrap_value(value.value))
            else:
                wrapped_args.append(native_ref)
                refs.append((value, native_ref))
        else:
            wrapped_args.append(_wrap_value(value))

    return wrapped_args, refs


def _copy_refs_back(refs):
    for byref, native_ref in refs:
        value = _read_native_reference(native_ref)
        if _is_vector(byref.value):
            value = IRISVector(value, dtype=byref.value.dtype)
        byref.value = value

class NativeClassProxy:
    def __init__(self, class_name, db):
        self._class_name = class_name
        self._db = db

    def __getattr__(self, name):
        # Map `_` to `%` for the first character
        mapped_name = name.replace("_", "%", 1) if name.startswith("_") else name

        def method_proxy(*args):
            wrapped_args, refs = _wrap_args_with_refs(args, self._db)
            res = self._db.classMethodValue(
                self._class_name,
                mapped_name,
                *wrapped_args,
            )
            _copy_refs_back(refs)
            return wrap_result(res, self._db)

        return method_proxy

_CLASS_PROPERTIES_CACHE = {}
_STRING_PROPERTY_TYPES = {
    "%Library.String",
    "%Library.RawString",
    "%String",
    "%RawString",
}

def _get_class_properties(classname, db):
    if classname in _CLASS_PROPERTIES_CACHE:
        return _CLASS_PROPERTIES_CACHE[classname]
        
    props = {}
    try:
        sql = "SELECT Name, Type, RuntimeType, Collection FROM %Dictionary.CompiledProperty WHERE parent = ?"
        rs = db.classMethodObject("%SQL.Statement", "%ExecDirect", None, sql, classname)
        while rs.invoke("%Next"):
            name = rs.get("Name")
            props[name] = {
                "type": rs.get("Type"),
                "runtime_type": rs.get("RuntimeType"),
                "collection": rs.get("Collection"),
            }
    except Exception:
        pass
        
    _CLASS_PROPERTIES_CACHE[classname] = props
    return props


def _is_string_property(metadata):
    if not metadata:
        return False

    # Keep collection-valued properties untouched. Some collection proxies may
    # use None to mean "missing" and should not be coerced into empty strings.
    if metadata.get("collection") is not None:
        return False

    for key in ("runtime_type", "type"):
        type_name = metadata.get(key)
        if type_name in _STRING_PROPERTY_TYPES:
            return True

    return False

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
            if val is None and _is_string_property(props.get(mapped_name)):
                return ""
            return wrap_result(val, self._db)
        else:
            def method_proxy(*args):
                wrapped_args, refs = _wrap_args_with_refs(args, self._db)
                res = self._oref.invoke(mapped_name, *wrapped_args)
                _copy_refs_back(refs)
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
