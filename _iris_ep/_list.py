from __future__ import annotations

import importlib
from collections.abc import Iterable, Sequence
from typing import Any

_MISSING = object()

# The $LIST codec is provided by the official InterSystems native SDK
# (``intersystems-irispython``), exposed as ``iris._elsdk_.IRISList`` /
# ``iris.irissdk.IRISList``.  It is resolved lazily on first use because, during
# ``import iris`` bootstrap, this module is imported before the wrapper extends
# ``iris.__path__`` to make those official submodules importable.  The legacy
# pure-Python ``intersystems_iris.IRISList`` is used only as a last-resort
# fallback when the native SDK is unavailable.
_NATIVE_LIST_CLASS: Any = None
_NATIVE_LIST_CANDIDATES = ("iris._elsdk_", "iris.irissdk", "intersystems_iris")


def _native_list_class():
    """Return the native $LIST codec class, importing it lazily once."""
    global _NATIVE_LIST_CLASS
    if _NATIVE_LIST_CLASS is not None:
        return _NATIVE_LIST_CLASS

    # Best effort: ensure the wrapper has extended iris.__path__ so the official
    # native submodules become importable.
    try:
        importlib.import_module("iris")
    except Exception:
        pass

    for module_name in _NATIVE_LIST_CANDIDATES:
        try:
            module = importlib.import_module(module_name)
        except Exception:
            continue
        native_cls = getattr(module, "IRISList", None)
        if native_cls is not None and native_cls is not IRISList:
            _NATIVE_LIST_CLASS = native_cls
            return native_cls

    raise RuntimeError(
        "No IRIS $LIST codec is available. Install 'intersystems-irispython' "
        "to provide iris.irissdk.IRISList."
    )


def _is_iris_list_like(value: Any) -> bool:
    if isinstance(value, IRISList):
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


def _decode_buffer(buffer: bytes) -> list[Any]:
    """Decode a $LIST buffer into a list of Python values via the native codec.

    Nested sublists are returned as scalars (matching the historical behavior),
    because the native ``getIRISList`` cannot safely materialize a sublist
    parsed from a buffer.  Live nested ``IRISList`` objects are only preserved
    through in-memory operations, never through a buffer round-trip.
    """
    if not buffer:
        return []
    native = _native_list_class()(buffer)
    items: list[Any] = []
    for index in range(1, native.count() + 1):
        try:
            items.append(native.get(index))
        except Exception:
            items.append(native.getBytes(index))
    return items


def _coerce_native_iris_list_class(native_cls: Any = None):
    if native_cls is None or native_cls is IRISList:
        return _native_list_class()
    return native_cls


def _get_native_iris_list_class(db: Any = None):
    return _native_list_class()


class IRISList(Sequence):
    """Python value wrapper for IRIS ``$LIST`` values.

    Backed by the official native SDK ``$LIST`` codec for serialization while
    keeping element structure in a plain Python list, so slicing, insertion,
    and nesting work without relying on native operations that cannot round-trip
    sublists.
    """

    def __init__(
        self,
        values: Any = None,
        *,
        locale: str = "latin-1",
        is_unicode: bool = True,
        compact_double: bool = False,
    ):
        # locale/is_unicode/compact_double are retained for API compatibility;
        # the native codec manages encoding internally.
        self._locale = locale
        self._is_unicode = is_unicode
        self.compact_double = compact_double
        self._items: list[Any] = []

        if values is None:
            return

        if isinstance(values, IRISList):
            self._items = values._copy_items()
            return

        if isinstance(values, (bytes, bytearray, memoryview)):
            self._items = _decode_buffer(_list_bytes_from_db(values))
            return

        if _is_iris_list_like(values):
            self._items = _decode_buffer(bytes(values.getBuffer()))
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

    # -- construction helpers ------------------------------------------------

    @classmethod
    def from_db(cls, value: Any) -> "IRISList":
        return cls.from_buffer(_list_bytes_from_db(value))

    @classmethod
    def from_buffer(cls, value: Any) -> "IRISList":
        return cls(_list_bytes_from_db(value))

    def _coerce(self, value: Any) -> Any:
        if isinstance(value, IRISList):
            return value
        if _is_iris_list_like(value):
            return IRISList.from_buffer(bytes(value.getBuffer()))
        return value

    def _copy_items(self) -> list[Any]:
        return [
            item.copy() if isinstance(item, IRISList) else item
            for item in self._items
        ]

    # -- index helpers -------------------------------------------------------

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

    # -- native ($LIST) one-based API ----------------------------------------

    def add(self, value: Any):
        self._items.append(self._coerce(value))
        return self

    def set(self, index: int, value: Any):
        if index > len(self._items):
            self._items.extend([None] * (index - len(self._items)))
        self._items[index - 1] = self._coerce(value)
        return self

    def get(self, index: int):
        return self._items[index - 1]

    def remove(self, index: int):
        del self._items[index - 1]
        return self

    def getBuffer(self) -> bytes:
        native_cls = _native_list_class()
        native = native_cls()
        for item in self._items:
            if isinstance(item, IRISList):
                native.add(native_cls(item.getBuffer()))
            else:
                native.add(item)
        return native.getBuffer()

    def getIRISList(self, index: int):
        item = self._items[index - 1]
        if item is None:
            return None
        if isinstance(item, IRISList):
            return item.copy()
        native_cls = _native_list_class()
        element = native_cls()
        element.add(item)
        return IRISList(
            element.getBuffer(),
            locale=self._locale,
            is_unicode=self._is_unicode,
            compact_double=self.compact_double,
        )

    # -- Python sequence protocol --------------------------------------------

    def __len__(self):
        return len(self._items)

    def __iter__(self):
        return iter(self._items)

    def __getitem__(self, index):
        if isinstance(index, slice):
            return [self._items[position] for position in range(*index.indices(len(self)))]
        return self._items[self._python_index(index)]

    def __setitem__(self, index, value):
        if isinstance(index, slice):
            try:
                values = [self._coerce(item) for item in value]
            except TypeError as exc:
                raise TypeError(
                    "can only assign an iterable to an IRISList slice"
                ) from exc
            self._items[index] = values
            return
        self._items[self._python_index(index)] = self._coerce(value)

    def __delitem__(self, index):
        if isinstance(index, slice):
            del self._items[index]
            return
        del self._items[self._python_index(index)]

    def __contains__(self, value):
        return any(item == value for item in self._items)

    def __reversed__(self):
        return reversed(self._items)

    def __repr__(self):
        return f"IRISList({self._items!r})"

    def __eq__(self, other):
        if _is_iris_list_like(other):
            return self.getBuffer() == bytes(other.getBuffer())
        if isinstance(other, Sequence) and not isinstance(
            other, (str, bytes, bytearray, memoryview)
        ):
            return list(self) == list(other)
        return NotImplemented

    def __ne__(self, other):
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result

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
        self._items = [self._coerce(value) for value in list(self) * count]
        return self

    def equals(self, irislist2):
        if not _is_iris_list_like(irislist2):
            raise TypeError("Argument must be an instance of IRISList")
        return self == irislist2

    # -- list-like mutators --------------------------------------------------

    def append(self, value: Any) -> None:
        self._items.append(self._coerce(value))

    def extend(self, values: Iterable[Any]) -> None:
        for value in values:
            self._items.append(self._coerce(value))

    def insert(self, index: int, value: Any) -> None:
        self._items.insert(self._insert_index(index), self._coerce(value))

    def pop(self, index: int = -1):
        if not self._items:
            raise IndexError("pop from empty IRISList")
        normalized_index = self._python_index(index)
        value = self._items[normalized_index]
        del self._items[normalized_index]
        return value

    def index(self, value: Any, start: int = 0, stop: Any = None) -> int:
        length = len(self)
        if stop is None:
            stop = length
        start, stop, _ = slice(start, stop).indices(length)
        for index in range(start, stop):
            if self._items[index] == value:
                return index
        raise ValueError(f"{value!r} is not in IRISList")

    def count(self, value: Any = _MISSING) -> int:
        if value is _MISSING:
            return len(self._items)
        return sum(1 for item in self._items if item == value)

    def copy(self) -> "IRISList":
        copied = IRISList(
            locale=self._locale,
            is_unicode=self._is_unicode,
            compact_double=self.compact_double,
        )
        copied._items = self._copy_items()
        return copied

    # -- conversions ---------------------------------------------------------

    def to_list(self) -> list[Any]:
        return list(self._items)

    def to_param(self) -> bytes:
        return self.getBuffer()

    def to_native(self, native_cls: Any = None):
        native_cls = _coerce_native_iris_list_class(native_cls)
        return native_cls(self.getBuffer())
