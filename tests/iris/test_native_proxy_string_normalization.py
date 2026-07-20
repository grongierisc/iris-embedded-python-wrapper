import pytest

from iris_utils import _iris_native_proxy as native_proxy


class FakeOref:
    def __init__(self, values):
        self._values = values

    def invoke(self, method_name, *args):
        if method_name == "%ClassName":
            return "Demo.StringProbe"
        raise AssertionError(f"Unexpected method call: {method_name}")

    def get(self, prop_name):
        return self._values.get(prop_name)


class FakePropertyResult:
    def __init__(self, property_name):
        self._property_name = property_name
        self._advanced = False

    def invoke(self, method_name):
        assert method_name == "%Next"
        if self._advanced:
            return False
        self._advanced = True
        return True

    def get(self, property_name):
        values = {
            "Name": self._property_name,
            "Type": "%Library.String",
            "RuntimeType": "%Library.String",
            "Collection": None,
        }
        return values[property_name]


class FakePropertyDb:
    def __init__(self, property_name="Value", failures=0, namespace="USER"):
        self.property_name = property_name
        self.failures = failures
        self._namespace = namespace
        self.calls = 0

    def classMethodObject(self, *args):
        self.calls += 1
        if self.calls <= self.failures:
            raise RuntimeError("metadata unavailable")
        return FakePropertyResult(self.property_name)


@pytest.fixture(autouse=True)
def clear_property_cache():
    with native_proxy._CLASS_PROPERTIES_CACHE_LOCK:
        native_proxy._CLASS_PROPERTIES_CACHE.clear()


def test_native_string_property_none_normalizes_to_empty_string(monkeypatch):
    proxy = native_proxy.NativeObjectProxy(FakeOref({"StringValue": None}), db=object())

    monkeypatch.setattr(
        native_proxy,
        "_get_class_properties",
        lambda classname, db: {
            "StringValue": {
                "type": "%Library.String",
                "runtime_type": "%Library.String",
                "collection": None,
            }
        },
    )

    assert proxy.StringValue == ""


def test_native_non_string_property_none_remains_none(monkeypatch):
    proxy = native_proxy.NativeObjectProxy(FakeOref({"Counter": None}), db=object())

    monkeypatch.setattr(
        native_proxy,
        "_get_class_properties",
        lambda classname, db: {
            "Counter": {
                "type": "%Library.Integer",
                "runtime_type": "%Library.Integer",
                "collection": None,
            }
        },
    )

    assert proxy.Counter is None


def test_native_string_collection_none_is_not_coerced(monkeypatch):
    proxy = native_proxy.NativeObjectProxy(FakeOref({"Tags": None}), db=object())

    monkeypatch.setattr(
        native_proxy,
        "_get_class_properties",
        lambda classname, db: {
            "Tags": {
                "type": "%Library.String",
                "runtime_type": "%Library.String",
                "collection": "list",
            }
        },
    )

    assert proxy.Tags is None


def test_property_metadata_cache_is_scoped_to_connection_and_namespace():
    first = FakePropertyDb("First")
    second = FakePropertyDb("Second")

    assert "First" in native_proxy._get_class_properties("Demo.Class", first)
    assert "Second" in native_proxy._get_class_properties("Demo.Class", second)

    first._namespace = "OTHER"
    first.property_name = "OtherNamespace"
    assert "OtherNamespace" in native_proxy._get_class_properties("Demo.Class", first)
    assert first.calls == 2


def test_failed_property_metadata_probe_is_not_cached():
    db = FakePropertyDb(failures=1)

    assert native_proxy._get_class_properties("Demo.Class", db) == {}
    assert "Value" in native_proxy._get_class_properties("Demo.Class", db)
    assert db.calls == 2


def test_wrap_result_uses_iris_capabilities_not_python_class_name():
    value = FakeOref({})

    wrapped = native_proxy.wrap_result(value, object())

    assert isinstance(wrapped, native_proxy.NativeObjectProxy)


def test_selected_stream_conversion_preserves_failure_cause():
    class BrokenStream:
        def invoke(self, method_name, *args):
            if method_name == "%ClassName":
                return "%Stream.GlobalCharacter"
            raise OSError("stream read failed")

    with pytest.raises(RuntimeError, match="Failed to read IRIS") as excinfo:
        native_proxy.wrap_result(BrokenStream(), object())

    assert isinstance(excinfo.value.__cause__, OSError)


def test_selected_dynamic_conversion_preserves_failure_cause():
    class DynamicValue:
        def invoke(self, method_name, *args):
            if method_name == "%ClassName":
                return "%Library.DynamicObject"
            raise AssertionError(method_name)

    class BrokenDb:
        def classMethodValue(self, *args):
            raise OSError("stream creation failed")

    with pytest.raises(RuntimeError, match="Failed to deserialize IRIS") as excinfo:
        native_proxy.wrap_result(DynamicValue(), BrokenDb())

    assert isinstance(excinfo.value.__cause__, OSError)
