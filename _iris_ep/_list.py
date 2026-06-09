from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

import intersystems_iris


_BaseIRISList = intersystems_iris.IRISList
_MISSING = object()


def _is_iris_list_like(value: Any) -> bool:
    if isinstance(value, _BaseIRISList):
        return True
    return (
        value is not None
        and value.__class__.__name__ == "IRISList"
        and callable(getattr(value, "getBuffer", None))
    )


def _list_bytes_from_db(value: Any) -> bytes:
    if isinstance(value, IRISList):
        return value.getBuffer()
    if _is_iris_list_like(value):
        return bytes(value.getBuffer())
    if isinstance(value, bytes):
        return value
    if isinstance(value, bytearray):
        return bytes(value)
    if isinstance(value, memoryview):
        return value.tobytes()
    if isinstance(value, str):
        return value.encode("latin-1")
    raise TypeError(
        "IRISList database values must be bytes, strings, or IRISList objects"
    )


def _coerce_native_iris_list_class(native_cls: Any = None):
    if native_cls is None or native_cls is IRISList:
        return _BaseIRISList
    return native_cls


def _get_native_iris_list_class(db: Any = None):
    module_names: list[str] = []
    db_module = getattr(type(db), "__module__", "")
    if db_module:
        root_module = db_module.split(".", 1)[0]
        if root_module == "iris":
            module_names.extend(("iris._elsdk_", "iris._init_elsdk", "iris"))
        else:
            module_names.append(root_module)

    module_names.extend(("iris._elsdk_", "iris._init_elsdk", "intersystems_iris"))

    seen = set()
    for module_name in module_names:
        if module_name in seen:
            continue
        seen.add(module_name)
        try:
            module = __import__(module_name, fromlist=["IRISList"])
        except Exception:
            continue
        native_cls = getattr(module, "IRISList", None)
        if native_cls is not None and native_cls is not IRISList:
            return native_cls

    return _BaseIRISList


class IRISList(_BaseIRISList):
    """Python value wrapper for IRIS $LIST values."""

    def __init__(
        self,
        values: Any = None,
        *,
        locale: str = "latin-1",
        is_unicode: bool = True,
        compact_double: bool = False,
    ):
        super().__init__(
            None,
            locale=locale,
            is_unicode=is_unicode,
            compact_double=compact_double,
        )
        if values is None:
            return

        if isinstance(values, (bytes, bytearray, memoryview)):
            parsed = _BaseIRISList(
                _list_bytes_from_db(values),
                locale=locale,
                is_unicode=is_unicode,
                compact_double=compact_double,
            )
            self._list_data = list(parsed._list_data)
            return

        if _is_iris_list_like(values):
            parsed = _BaseIRISList(
                bytes(values.getBuffer()),
                locale=locale,
                is_unicode=is_unicode,
                compact_double=compact_double,
            )
            self._list_data = list(parsed._list_data)
            return

        if isinstance(values, str):
            self.add(values)
            return

        try:
            iterator = iter(values)
        except TypeError as exc:
            raise TypeError(
                "IRISList values must be an iterable or $LIST bytes"
            ) from exc

        for value in iterator:
            self.add(value)

    @classmethod
    def from_db(cls, value: Any) -> "IRISList":
        return cls.from_buffer(_list_bytes_from_db(value))

    @classmethod
    def from_buffer(cls, value: Any) -> "IRISList":
        return cls(_list_bytes_from_db(value))

    def _convertToInternal(self, value: Any):
        if isinstance(value, IRISList):
            return _BaseIRISList(
                value.getBuffer(),
                value._locale,
                value._is_unicode,
                value.compact_double,
            )
        if _is_iris_list_like(value):
            return _BaseIRISList(
                bytes(value.getBuffer()),
                self._locale,
                self._is_unicode,
                getattr(value, "compact_double", False),
            )
        return super()._convertToInternal(value)

    def _python_index(self, index: int) -> int:
        if not isinstance(index, int):
            raise TypeError("IRISList indices must be integers or slices")
        if index < 0:
            index += len(self)
        if index < 0 or index >= len(self):
            raise IndexError("IRISList index out of range")
        return index

    def _insert_index(self, index: int) -> int:
        if not isinstance(index, int):
            raise TypeError("IRISList indices must be integers")
        length = len(self)
        if index < 0:
            return max(0, index + length)
        return min(index, length)

    def add(self, value: Any):
        self._list_data.append(self._convertToInternal(value))
        return self

    def set(self, index: int, value: Any):
        if index > len(self._list_data):
            self._list_data.extend([None] * (index - len(self._list_data)))
        self._list_data[index - 1] = self._convertToInternal(value)
        return self

    def get(self, index: int):
        raw_data = self._list_data[index - 1]
        if _is_iris_list_like(raw_data):
            return IRISList(
                raw_data.getBuffer(),
                locale=self._locale,
                is_unicode=self._is_unicode,
                compact_double=getattr(raw_data, "compact_double", self.compact_double),
            )
        return super().get(index)

    def getIRISList(self, index: int):
        raw_data = self._list_data[index - 1]
        if raw_data is None:
            return None
        if _is_iris_list_like(raw_data):
            return IRISList(
                raw_data.getBuffer(),
                locale=self._locale,
                is_unicode=self._is_unicode,
                compact_double=getattr(raw_data, "compact_double", self.compact_double),
            )
        return IRISList(
            intersystems_iris.IRIS._convertToBytes(
                raw_data,
                intersystems_iris.IRIS.MODE_LIST,
                self._locale,
                self._is_unicode,
            ),
            locale=self._locale,
            is_unicode=self._is_unicode,
            compact_double=self.compact_double,
        )

    def __len__(self):
        return self.count()

    def __iter__(self):
        for index in range(1, self.count() + 1):
            yield self.get(index)

    def __getitem__(self, index):
        if isinstance(index, slice):
            return [self[position] for position in range(*index.indices(len(self)))]
        return self.get(self._python_index(index) + 1)

    def __setitem__(self, index, value):
        if isinstance(index, slice):
            try:
                values = [self._convertToInternal(item) for item in value]
            except TypeError as exc:
                raise TypeError(
                    "can only assign an iterable to an IRISList slice"
                ) from exc
            self._list_data[index] = values
            return
        self._list_data[self._python_index(index)] = self._convertToInternal(value)

    def __delitem__(self, index):
        if isinstance(index, slice):
            del self._list_data[index]
            return
        del self._list_data[self._python_index(index)]

    def __contains__(self, value):
        return any(item == value for item in self)

    def __reversed__(self):
        for index in range(len(self) - 1, -1, -1):
            yield self[index]

    def __repr__(self):
        return f"IRISList({list(self)!r})"

    def __eq__(self, other):
        if _is_iris_list_like(other):
            return self.getBuffer() == bytes(other.getBuffer())
        if isinstance(other, Sequence) and not isinstance(
            other, (str, bytes, bytearray, memoryview)
        ):
            return list(self) == list(other)
        return False

    def __add__(self, other):
        result = self.copy()
        result.extend(other)
        return result

    def __radd__(self, other):
        result = IRISList(other)
        result.extend(self)
        return result

    def __iadd__(self, other):
        self.extend(other)
        return self

    def __mul__(self, count):
        if not isinstance(count, int):
            return NotImplemented
        return IRISList(list(self) * count)

    def __rmul__(self, count):
        return self.__mul__(count)

    def __imul__(self, count):
        if not isinstance(count, int):
            return NotImplemented
        self._list_data = [
            self._convertToInternal(value) for value in list(self) * count
        ]
        return self

    def equals(self, irislist2):
        if not _is_iris_list_like(irislist2):
            raise TypeError("Argument must be an instance of IRISList")
        return self == irislist2

    def append(self, value: Any) -> None:
        self._list_data.append(self._convertToInternal(value))

    def extend(self, values: Iterable[Any]) -> None:
        for value in values:
            self._list_data.append(self._convertToInternal(value))

    def insert(self, index: int, value: Any) -> None:
        self._list_data.insert(
            self._insert_index(index),
            self._convertToInternal(value),
        )

    def pop(self, index: int = -1):
        if not self:
            raise IndexError("pop from empty IRISList")
        normalized_index = self._python_index(index)
        value = self[normalized_index]
        del self._list_data[normalized_index]
        return value

    def index(self, value: Any, start: int = 0, stop: Any = None) -> int:
        length = len(self)
        if stop is None:
            stop = length
        start, stop, _ = slice(start, stop).indices(length)
        for index in range(start, stop):
            if self[index] == value:
                return index
        raise ValueError(f"{value!r} is not in IRISList")

    def count(self, value: Any = _MISSING) -> int:
        if value is _MISSING:
            return super().count()
        return sum(1 for item in self if item == value)

    def copy(self) -> "IRISList":
        copied = IRISList(
            locale=self._locale,
            is_unicode=self._is_unicode,
            compact_double=self.compact_double,
        )
        copied._list_data = [
            (
                _BaseIRISList(
                    value.getBuffer(),
                    self._locale,
                    self._is_unicode,
                    getattr(value, "compact_double", self.compact_double),
                )
                if _is_iris_list_like(value)
                else value
            )
            for value in self._list_data
        ]
        return copied

    def to_list(self) -> list[Any]:
        return list(self)

    def to_param(self) -> bytes:
        return self.getBuffer()

    def to_native(self, native_cls: Any = None):
        native_cls = _coerce_native_iris_list_class(native_cls)
        return native_cls(self.getBuffer())
