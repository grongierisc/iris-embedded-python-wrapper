import json
import logging
from collections import OrderedDict
from threading import RLock

try:
    from _iris_ep._byref import ByRef
except Exception:  # pragma: no cover - iris_utils can be imported standalone.
    ByRef = None

try:
    from _iris_ep._vector import IRISVector
except Exception:  # pragma: no cover - iris_utils can be imported standalone.
    IRISVector = None

try:
    from _iris_ep._list import IRISList, _get_native_iris_list_class
except Exception:  # pragma: no cover - iris_utils can be imported standalone.
    IRISList = None
    _get_native_iris_list_class = None


logger = logging.getLogger(__name__)

_DYNAMIC_CLASSES = {"%Library.DynamicObject", "%Library.DynamicArray"}
_STREAM_CLASSES = {
    "%Stream.GlobalBinary",
    "%Stream.GlobalCharacter",
    "%Stream.FileBinary",
    "%Stream.FileCharacter",
}


def _iris_classname(value):
    if isinstance(value, NativeObjectProxy):
        return None
    invoke = getattr(value, "invoke", None)
    if not callable(invoke):
        return None
    try:
        classname = invoke("%ClassName", 1)
    except Exception:
        # Older native drivers are identifiable only by their concrete wrapper
        # type and may not expose %ClassName for every object.
        return "" if value.__class__.__name__ == "IRISObject" else None
    if not isinstance(classname, str):
        return None
    if classname and "." not in classname and not classname.startswith("%"):
        return None
    return classname


def _dynamic_to_python(value, db):
    stream = db.classMethodValue("%Stream.GlobalCharacter", "%New")
    value.invoke("%ToJSON", stream)
    stream.invoke("Rewind")
    size = stream.get("Size")
    content = stream.invoke("Read", size) if size and size > 0 else ""
    return json.loads(content)


def _stream_to_python(value, classname):
    value.invoke("Rewind")
    size = value.get("Size")
    if not size:
        return b"" if "Binary" in classname else ""
    content = value.invoke("Read", size)
    if "Binary" in classname and isinstance(content, str):
        return content.encode("latin1")
    return content


def wrap_result(res, db):
    """
    Wraps the result from Native API if it is an IRISObject.
    Automatically unwraps streams and dynamic objects into Python primitives.
    """
    classname = _iris_classname(res)
    if classname is None:
        return res

    if classname in _DYNAMIC_CLASSES:
        try:
            return _dynamic_to_python(res, db)
        except Exception as exc:
            raise RuntimeError(f"Failed to deserialize IRIS {classname}") from exc

    if classname in _STREAM_CLASSES:
        try:
            return _stream_to_python(res, classname)
        except Exception as exc:
            raise RuntimeError(f"Failed to read IRIS {classname}") from exc

    return NativeObjectProxy(res, db)


def _is_vector(value):
    return IRISVector is not None and isinstance(value, IRISVector)


def _is_iris_list(value):
    return IRISList is not None and isinstance(value, IRISList)


def _wrap_value(value, db=None):
    if isinstance(value, NativeObjectProxy):
        return value._oref
    if _is_vector(value):
        return value.to_param()
    if _is_iris_list(value):
        native_cls = (
            _get_native_iris_list_class(db)
            if callable(_get_native_iris_list_class)
            else None
        )
        return value.to_native(native_cls)
    return value


def _wrap_args(args, db):
    return [_wrap_value(value, db) for value in args]


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

    if IRISList is not None and (
        _is_iris_list(value.value) or value.type is IRISList
    ):
        raise RuntimeError(
            "Native ByRef IRISList is not supported because the native "
            "IRISReference value path cannot reliably materialize IRISList values"
        )

    native_value = _wrap_value(value.value, db)
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
                wrapped_args.append(_wrap_value(value.value, db))
            else:
                wrapped_args.append(native_ref)
                refs.append((value, native_ref))
        else:
            wrapped_args.append(_wrap_value(value, db))

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

_CLASS_PROPERTIES_CACHE_MAXSIZE = 256
_CLASS_PROPERTIES_CACHE = OrderedDict()
_CLASS_PROPERTIES_CACHE_LOCK = RLock()
_STRING_PROPERTY_TYPES = {
    "%Library.String",
    "%Library.RawString",
    "%String",
    "%RawString",
}

def _class_properties_cache_key(classname, db):
    try:
        state = vars(db)
    except Exception:
        state = {}
    namespace = state.get("_namespace", state.get("namespace"))
    try:
        hash(db)
        connection = db
    except Exception:
        connection = id(db)
    return connection, str(namespace) if namespace is not None else None, classname


def _get_class_properties(classname, db):
    cache_key = _class_properties_cache_key(classname, db)
    with _CLASS_PROPERTIES_CACHE_LOCK:
        cached = _CLASS_PROPERTIES_CACHE.get(cache_key)
        if cached is not None:
            _CLASS_PROPERTIES_CACHE.move_to_end(cache_key)
            return cached

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
        logger.debug("Unable to probe properties for %s", classname, exc_info=True)
        return props

    with _CLASS_PROPERTIES_CACHE_LOCK:
        _CLASS_PROPERTIES_CACHE[cache_key] = props
        _CLASS_PROPERTIES_CACHE.move_to_end(cache_key)
        while len(_CLASS_PROPERTIES_CACHE) > _CLASS_PROPERTIES_CACHE_MAXSIZE:
            _CLASS_PROPERTIES_CACHE.popitem(last=False)
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
        value = _wrap_value(value, self._db)

        mapped_name = name.replace("_", "%", 1) if name.startswith("_") else name
        self._oref.set(mapped_name, value)
