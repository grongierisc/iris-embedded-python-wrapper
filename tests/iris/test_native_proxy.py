import pytest
from unittest.mock import MagicMock
import iris_embedded_python as iris
import _iris_ep
import iris_ep

# A mock for the IRISObject class that would be returned by Native API
class MockIRISObject:
    def __init__(self, db=None, class_name="iris.IRISObject"):
        self._db = db
        # Native API objects have "__class__.__name__ == 'IRISObject'" 
        self.__class__.__name__ = "IRISObject"

    def invoke(self, method_name, *args):
        if method_name == "%ClassName":
            return "User.Bar"
        if self._db is not None:
            return self._db.invoke(self, method_name, *args)
        return "MethodSuccess"

    def get(self, prop_name):
        if self._db is not None:
            return self._db.get(self, prop_name)
        return "Value"

    def set(self, prop_name, value):
        if self._db is not None:
            self._db.set(self, prop_name, value)


class MockPropertyResult:
    def __init__(self, rows):
        self.rows = rows
        self.index = -1

    def invoke(self, method_name, *args):
        if method_name != "%Next":
            raise Exception("Method not found")
        self.index += 1
        return self.index < len(self.rows)

    def get(self, prop_name):
        return self.rows[self.index].get(prop_name)
        
class MockIRISNativeConnection:
    def __init__(self):
        self.invoked_methods = []
        self.get_props = []
        self.set_props = []
        
    def invokeClassMethod(self, class_name, method_name, *args):
        self.invoked_methods.append((class_name, method_name, args))
        if class_name == "User.Bar" and method_name == "%OpenId":
            return MockIRISObject(db=self)
        if class_name == "User.Bar" and method_name == "Foo":
            args[1].setValue(42)
            return 1
        return "Success"

    def classMethodValue(self, class_name, method_name, *args):
        return self.invokeClassMethod(class_name, method_name, *args)

    def classMethodObject(self, class_name, method_name, *args):
        if class_name == "%SQL.Statement" and method_name == "%ExecDirect":
            return MockPropertyResult([
                {
                    "Name": "Name",
                    "Type": "%Library.String",
                    "RuntimeType": "%Library.String",
                    "Collection": None,
                },
                {
                    "Name": "%State",
                    "Type": "%Library.String",
                    "RuntimeType": "%Library.String",
                    "Collection": None,
                },
                {
                    "Name": "Payload",
                    "Type": "%Library.DynamicObject",
                    "RuntimeType": "%Library.DynamicObject",
                    "Collection": None,
                },
                {
                    "Name": "Blob",
                    "Type": "%Library.Binary",
                    "RuntimeType": "%Library.Binary",
                    "Collection": None,
                },
            ])
        raise Exception("Method not found")
        
    def invoke(self, oref, method_name, *args):
        self.invoked_methods.append(("Instance", method_name, args))
        if method_name == "%Save":
            return 1
        if method_name == "Foo":
            args[0].setValue(99)
            return 1
        return "MethodSuccess"
        
    def get(self, oref, prop_name):
        self.get_props.append(prop_name)
        if prop_name == "Name":
            return "TestName"
        # Simulate property not existing by raising an Exception
        raise Exception("Property not found")
        
    def set(self, oref, prop_name, value):
        self.set_props.append((prop_name, value))


class MockIRISConnection:
    def isConnected(self):
        return True


class MockIRISHandleLikeConnection:
    def __init__(self):
        self.invoked_methods = []
        self.get_props = []
        self.set_props = []

    def isConnected(self):
        return True

    def invokeClassMethod(self, class_name, method_name, *args):
        self.invoked_methods.append((class_name, method_name, args))
        return "Success"

    def classMethodValue(self, class_name, method_name, *args):
        return self.invokeClassMethod(class_name, method_name, *args)

    def invoke(self, oref, method_name, *args):
        return "MethodSuccess"

    def get(self, oref, prop_name):
        return "Value"

    def set(self, oref, prop_name, value):
        self.set_props.append((prop_name, value))


def test_native_api_proxy_cls():
    db = MockIRISNativeConnection()
    
    iris.runtime.configure(mode="native", iris=db)
    
    try:
        # 2. Test class mapping
        bar_class = iris.cls("User.Bar")
        
        # Test class method call
        obj = bar_class._OpenId(1)
        assert db.invoked_methods[0] == ("User.Bar", "%OpenId", (1,))
        
        # Ensure returned object is wrapped
        assert obj.__class__.__name__ == "NativeObjectProxy"
        
        # Test property getter (valid)
        assert obj.Name == "TestName"
        assert "Name" in db.get_props
        
        # Test property getter (invalid -> fallback to method)
        res = obj._Save()
        assert res == 1
        assert db.invoked_methods[-1] == ("Instance", "%Save", ())
        
        # Test property setter
        obj.Name = "NewName"
        assert ("Name", "NewName") in db.set_props
        
        obj._State = "Saved"
        assert ("%State", "Saved") in db.set_props

    finally:
        iris.runtime.reset()


def test_runtime_reset_clears_native_handle():
    db = MockIRISNativeConnection()

    iris.runtime.configure(mode="native", iris=db)
    assert iris.runtime.iris is db
    assert iris.runtime.mode == "native"

    iris.runtime.reset()

    assert iris.runtime.iris is None
    assert iris.runtime.mode == "auto"


def test_native_proxy_class_method_supports_byref():
    db = MockIRISNativeConnection()
    ref = iris.ByRef(0, int)

    iris.runtime.configure(mode="native", iris=db)

    try:
        result = iris.cls("User.Bar").Foo("input", ref)
    finally:
        iris.runtime.reset()

    assert result == 1
    assert ref.value == 42
    class_name, method_name, args = db.invoked_methods[-1]
    assert (class_name, method_name) == ("User.Bar", "Foo")
    assert args[0] == "input"
    assert args[1] is not ref
    assert hasattr(args[1], "setValue")
    assert args[1].get_type() is int


def test_native_proxy_class_method_supports_public_ref():
    db = MockIRISNativeConnection()

    iris.runtime.configure(mode="native", iris=db)

    try:
        ref = iris.ref(0)
        result = iris.cls("User.Bar").Foo("input", ref)
    finally:
        iris.runtime.reset()

    assert result == 1
    assert isinstance(ref, iris.ByRef)
    assert ref.value == 42


def test_native_proxy_instance_method_supports_byref():
    db = MockIRISNativeConnection()
    ref = iris.ByRef(0, int)

    iris.runtime.configure(mode="native", iris=db)

    try:
        obj = iris.cls("User.Bar")._OpenId(1)
        result = obj.Foo(ref)
    finally:
        iris.runtime.reset()

    assert result == 1
    assert ref.value == 99
    target, method_name, args = db.invoked_methods[-1]
    assert (target, method_name) == ("Instance", "Foo")
    assert args[0] is not ref
    assert hasattr(args[0], "setValue")
    assert args[0].get_type() is int


def test_native_proxy_converts_vector_method_args():
    db = MockIRISNativeConnection()
    vector = iris.Vector([1, 2, 3])

    iris.runtime.configure(mode="native", iris=db)

    try:
        iris.cls("User.Bar").VectorArg(vector)
        obj = iris.cls("User.Bar")._OpenId(1)
        obj.VectorArg(vector)
    finally:
        iris.runtime.reset()

    assert db.invoked_methods[-3] == ("User.Bar", "VectorArg", ("1,2,3",))
    assert db.invoked_methods[-1] == ("Instance", "VectorArg", ("1,2,3",))


def test_native_proxy_converts_iris_list_method_args():
    db = MockIRISNativeConnection()
    payload = iris.IRISList([1, "two"])

    iris.runtime.configure(mode="native", iris=db)

    try:
        iris.cls("User.Bar").ListArg(payload)
        obj = iris.cls("User.Bar")._OpenId(1)
        obj.ListArg(payload)
    finally:
        iris.runtime.reset()

    class_arg = db.invoked_methods[-3][2][0]
    instance_arg = db.invoked_methods[-1][2][0]

    assert db.invoked_methods[-3][:2] == ("User.Bar", "ListArg")
    assert db.invoked_methods[-1][:2] == ("Instance", "ListArg")
    assert class_arg is not payload
    assert instance_arg is not payload
    assert class_arg.__class__.__name__ == "IRISList"
    assert instance_arg.__class__.__name__ == "IRISList"
    assert class_arg.getBuffer() == payload.getBuffer()
    assert instance_arg.getBuffer() == payload.getBuffer()


def test_native_proxy_rejects_iris_list_byref_copyback():
    db = MockIRISNativeConnection()
    ref = iris.ByRef(iris.IRISList([1, "two"]), iris.IRISList)

    iris.runtime.configure(mode="native", iris=db)

    try:
        with pytest.raises(RuntimeError, match="Native ByRef IRISList"):
            iris.cls("User.Bar").ListArg(ref)
    finally:
        iris.runtime.reset()

    assert db.invoked_methods == []


def test_vector_operations_do_not_use_native_runtime_bridge():
    db = MockIRISNativeConnection()

    iris.runtime.configure(mode="native", iris=db)

    try:
        with pytest.raises(RuntimeError, match="embedded runtime"):
            iris.Vector([1, 2, 3], dtype="float").sum()
        with pytest.raises(RuntimeError, match="embedded runtime"):
            iris.gref("^CacheTemp")
        with pytest.raises(RuntimeError, match="embedded runtime"):
            iris.execute("set x=1")
    finally:
        iris.runtime.reset()


def test_runtime_configure_accepts_native_connection_and_converts(monkeypatch):
    conn = MockIRISConnection()
    db = MockIRISNativeConnection()

    monkeypatch.setattr(_iris_ep, "createIRIS", lambda c: db if c is conn else None, raising=False)

    iris.runtime.configure(native_connection=conn)

    try:
        assert iris.runtime.mode == "native"
        assert iris.runtime.native_connection is conn
        assert iris.runtime.iris is db

        bar_class = iris.cls("User.Bar")
        bar_class._OpenId(1)
        assert db.invoked_methods[0] == ("User.Bar", "%OpenId", (1,))
    finally:
        iris.runtime.reset()


def test_runtime_configure_accepts_connection_passed_as_iris(monkeypatch):
    conn = MockIRISConnection()
    db = MockIRISNativeConnection()

    monkeypatch.setattr(_iris_ep, "createIRIS", lambda c: db if c is conn else None, raising=False)

    iris.runtime.configure(iris=conn)

    try:
        assert iris.runtime.mode == "native"
        assert iris.runtime.native_connection is conn
        assert iris.runtime.iris is db
    finally:
        iris.runtime.reset()


def test_runtime_configure_accepts_native_connection_already_iris_handle(monkeypatch):
    db = MockIRISHandleLikeConnection()

    # If createIRIS gets called here, the test should fail.
    monkeypatch.setattr(_iris_ep, "createIRIS", lambda _: (_ for _ in ()).throw(AssertionError("createIRIS should not be called")), raising=False)

    iris.runtime.configure(native_connection=db)

    try:
        assert iris.runtime.mode == "native"
        assert iris.runtime.iris is db

        iris.cls("User.Bar").OpenId(1)
        assert db.invoked_methods[0] == ("User.Bar", "OpenId", (1,))
    finally:
        iris.runtime.reset()


def test_native_proxy_does_not_auto_convert_method_args():
    db = MockIRISNativeConnection()

    iris.runtime.configure(mode="native", iris=db)

    try:
        bar_class = iris.cls("User.Bar")
        payload_dict = {"a": 1}
        payload_list = [1, 2]
        payload_bytes = b"abc"

        bar_class._OpenId(payload_dict, payload_list, payload_bytes)

        assert db.invoked_methods[0] == (
            "User.Bar",
            "%OpenId",
            (payload_dict, payload_list, payload_bytes),
        )
    finally:
        iris.runtime.reset()


def test_native_proxy_does_not_auto_convert_property_values():
    db = MockIRISNativeConnection()

    iris.runtime.configure(mode="native", iris=db)

    try:
        obj = iris.cls("User.Bar")._OpenId(1)
        payload_dict = {"k": "v"}
        payload_bytes = b"bin"

        obj.Payload = payload_dict
        obj.Blob = payload_bytes

        assert ("Payload", payload_dict) in db.set_props
        assert ("Blob", payload_bytes) in db.set_props
    finally:
        iris.runtime.reset()


def test_runtime_is_exported_from_wrapper_modules():
    assert hasattr(_iris_ep, "runtime")
    assert hasattr(iris_ep, "runtime")
    assert hasattr(iris, "runtime")

    assert _iris_ep.runtime is iris_ep.runtime
    assert iris_ep.runtime is iris.runtime

    current = iris.runtime.get()
    assert hasattr(current, "mode")
    assert hasattr(current, "state")
