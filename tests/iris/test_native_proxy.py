import pytest
from unittest.mock import MagicMock
import iris_embedded_python as iris
import _iris_ep

# A mock for the IRISObject class that would be returned by Native API
class MockIRISObject:
    def __init__(self, class_name="iris.IRISObject"):
        # Native API objects have "__class__.__name__ == 'IRISObject'" 
        self.__class__.__name__ = "IRISObject"
        
class MockIRISNativeConnection:
    def __init__(self):
        self.invoked_methods = []
        self.get_props = []
        self.set_props = []
        
    def invokeClassMethod(self, class_name, method_name, *args):
        self.invoked_methods.append((class_name, method_name, args))
        if class_name == "User.Bar" and method_name == "%OpenId":
            return MockIRISObject()
        return "Success"
        
    def invoke(self, oref, method_name, *args):
        self.invoked_methods.append(("Instance", method_name, args))
        if method_name == "%Save":
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
        assert len(db.invoked_methods) == 1
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
