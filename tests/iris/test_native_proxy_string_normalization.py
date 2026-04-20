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
