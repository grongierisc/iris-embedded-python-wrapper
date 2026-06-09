from decimal import Decimal

import pytest

import iris


def test_iris_list_python_sequence_protocol():
    payload = iris.IRISList([1, "two", Decimal("3.5")])

    assert payload == [1, "two", Decimal("3.5")]
    assert payload.to_list() == [1, "two", Decimal("3.5")]
    assert list(reversed(payload)) == [Decimal("3.5"), "two", 1]
    assert "two" in payload
    assert payload.index("two") == 1
    assert payload.count("two") == 1
    assert payload.count() == 3

    payload[1] = "dos"
    payload[-1] = Decimal("4.5")
    assert payload.to_list() == [1, "dos", Decimal("4.5")]

    payload[1:2] = ["two", "three"]
    assert payload[1:3] == ["two", "three"]
    assert payload.to_list() == [1, "two", "three", Decimal("4.5")]

    del payload[2]
    payload.insert(2, "three")
    assert payload.to_list() == [1, "two", "three", Decimal("4.5")]

    assert payload.append(None) is None
    assert payload.pop() is None
    assert payload.pop(1) == "two"

    payload.extend(["two", "four"])
    payload += ["five"]
    assert payload.to_list() == [1, "three", Decimal("4.5"), "two", "four", "five"]

    combined = payload + ["six"]
    assert isinstance(combined, iris.IRISList)
    assert combined.to_list() == [
        1,
        "three",
        Decimal("4.5"),
        "two",
        "four",
        "five",
        "six",
    ]

    repeated = iris.IRISList(["x"]) * 3
    assert isinstance(repeated, iris.IRISList)
    assert repeated.to_list() == ["x", "x", "x"]


def test_iris_list_pythonic_copy_and_nested_values():
    nested = iris.IRISList(["inner"])
    payload = iris.IRISList([nested])

    assert isinstance(payload[0], iris.IRISList)
    assert payload[0].to_list() == ["inner"]

    copy = payload.copy()
    assert copy is not payload
    assert copy == payload
    assert isinstance(copy[0], iris.IRISList)


def test_iris_list_python_errors():
    payload = iris.IRISList(["a"])

    with pytest.raises(IndexError):
        _ = payload[1]
    with pytest.raises(IndexError):
        payload.pop(1)
    with pytest.raises(IndexError, match="pop from empty"):
        iris.IRISList().pop()
    with pytest.raises(TypeError):
        payload[object()] = "bad"
    with pytest.raises(TypeError, match="iterable"):
        payload[0:1] = None
    with pytest.raises(ValueError, match="not in IRISList"):
        payload.index("missing")


def test_iris_list_native_methods_remain_one_based():
    payload = iris.IRISList(["a", "b"])

    assert payload.add("c") is payload
    assert payload.set(4, "d") is payload
    assert payload.to_list() == ["a", "b", "c", "d"]

    assert payload.remove(2) is payload
    assert payload.to_list() == ["a", "c", "d"]

