from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal
from typing import Any
from uuid import uuid4


_VECTOR_CACHE_GLOBAL = "iris_vector"
_IRIS_VECTOR_DTYPES = {
    "int": "integer",
    "integer": "integer",
    "decimal": "decimal",
    "double": "double",
    "float": "float",
}
_IRIS_VECTOR_OBJECTSCRIPT_DTYPES = {
    "integer": "integer",
    "decimal": "decimal",
    "double": "double",
    # SQL VECTOR supports FLOAT, but ObjectScript $VECTOR stores numeric
    # vectors as integer, decimal, or double.
    "float": "double",
}


def _normalize_iris_vector_dtype(dtype: Any) -> str:
    if dtype is int:
        return "integer"
    if dtype is float:
        return "double"
    if dtype is Decimal:
        return "decimal"

    normalized = str(dtype or "decimal").strip().lower()
    try:
        return _IRIS_VECTOR_DTYPES[normalized]
    except KeyError as exc:
        supported = ", ".join(sorted(_IRIS_VECTOR_DTYPES))
        raise ValueError(
            f"Unsupported IRIS vector dtype: {dtype!r}; expected one of: {supported}"
        ) from exc


def _parse_iris_vector_text(value: str) -> tuple[str, ...]:
    text = value.strip()
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1].strip()
    if not text:
        return ()
    return tuple(part.strip() for part in text.split(","))


def _coerce_iris_vector_item(value: Any, dtype: str):
    if value is None:
        raise ValueError("IRISVector values cannot contain None")
    if isinstance(value, bool):
        value = int(value)
    if dtype == "integer":
        return int(value)
    if dtype in ("double", "float"):
        return float(value)
    if dtype == "decimal":
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))
    return value


def _format_iris_vector_item(value: Any) -> str:
    if isinstance(value, bool):
        return str(int(value))
    return str(value)


def _looks_like_iris_vector_operand(value: Any) -> bool:
    if isinstance(value, IRISVector):
        return True
    if isinstance(value, str):
        text = value.strip()
        return "," in text or (text.startswith("[") and text.endswith("]"))
    if isinstance(value, (bytes, bytearray, memoryview)):
        return False
    return isinstance(value, Iterable)


def _coerce_iris_vector_operand(value: Any, dtype: str) -> "IRISVector":
    if isinstance(value, IRISVector):
        if value.dtype != dtype:
            raise ValueError(
                f"IRIS VECTOR operations require matching dtypes: {dtype!r} != {value.dtype!r}"
            )
        return value
    return IRISVector(value, dtype=dtype)


class IRISVector:
    """Python value wrapper for IRIS SQL VECTOR parameters and operations."""

    __slots__ = ("_objectscript_dtype", "_values", "dtype")

    def __init__(self, values: Any, dtype: Any = "decimal"):
        self.dtype = _normalize_iris_vector_dtype(dtype)
        self._objectscript_dtype = _IRIS_VECTOR_OBJECTSCRIPT_DTYPES[self.dtype]
        if isinstance(values, IRISVector):
            raw_values = values._values
        elif isinstance(values, str):
            raw_values = _parse_iris_vector_text(values)
        else:
            try:
                raw_values = tuple(values)
            except TypeError as exc:
                raise TypeError("IRISVector values must be a string or iterable") from exc

        if not raw_values:
            raise ValueError("IRISVector requires at least one value")
        self._values = tuple(
            _coerce_iris_vector_item(value, self.dtype) for value in raw_values
        )

    @classmethod
    def from_db(cls, value: Any, dtype: Any = "decimal") -> "IRISVector":
        return cls(value, dtype=dtype)

    @classmethod
    def from_string(cls, value: str, dtype: Any = "decimal") -> "IRISVector":
        return cls(value, dtype=dtype)

    def __iter__(self):
        return iter(self._values)

    def __len__(self):
        return len(self._values)

    def __getitem__(self, index):
        return self._values[index]

    def __repr__(self):
        return f"IRISVector({list(self._values)!r}, dtype={self.dtype!r})"

    def __str__(self):
        return self.to_param()

    def __eq__(self, other):
        if isinstance(other, IRISVector):
            return self.dtype == other.dtype and self._values == other._values
        return False

    def to_param(self) -> str:
        return ",".join(_format_iris_vector_item(value) for value in self._values)

    def to_json_array(self) -> str:
        return f"[{self.to_param()}]"

    def to_sql(self, placeholder: str = "?") -> str:
        return f"TO_VECTOR({placeholder}, {self.dtype})"

    def as_type(self, dtype: Any) -> "IRISVector":
        return IRISVector(self._values, dtype=dtype)

    def count(self):
        return _execute_iris_vector_operation("count", self, returns_vector=False)

    def min(self):
        return _execute_iris_vector_operation("min", self, returns_vector=False)

    def max(self):
        return _execute_iris_vector_operation("max", self, returns_vector=False)

    def sum(self):
        return _execute_iris_vector_operation("sum", self, returns_vector=False)

    def dot(self, other: Any):
        other_vector = _coerce_iris_vector_operand(other, self.dtype)
        return _execute_iris_vector_operation(
            "dot-product", self, other_vector, returns_vector=False
        )

    def cosine(self, other: Any):
        other_vector = _coerce_iris_vector_operand(other, self.dtype)
        return _execute_iris_vector_operation(
            "cosine-similarity", self, other_vector, returns_vector=False
        )

    def add(self, other: Any) -> "IRISVector":
        if _looks_like_iris_vector_operand(other):
            other_vector = _coerce_iris_vector_operand(other, self.dtype)
            return _execute_iris_vector_operation(
                "v+", self, other_vector, returns_vector=True
            )
        return _execute_iris_vector_operation("+", self, other, returns_vector=True)

    def subtract(self, other: Any) -> "IRISVector":
        if _looks_like_iris_vector_operand(other):
            other_vector = _coerce_iris_vector_operand(other, self.dtype)
            return _execute_iris_vector_operation(
                "v-", self, other_vector, returns_vector=True
            )
        return _execute_iris_vector_operation("-", self, other, returns_vector=True)

    def multiply(self, other: Any) -> "IRISVector":
        if _looks_like_iris_vector_operand(other):
            other_vector = _coerce_iris_vector_operand(other, self.dtype)
            return _execute_iris_vector_operation(
                "v*", self, other_vector, returns_vector=True
            )
        return _execute_iris_vector_operation("*", self, other, returns_vector=True)

    def divide(self, other: Any) -> "IRISVector":
        if _looks_like_iris_vector_operand(other):
            other_vector = _coerce_iris_vector_operand(other, self.dtype)
            return _execute_iris_vector_operation(
                "v/", self, other_vector, returns_vector=True
            )
        return _execute_iris_vector_operation("/", self, other, returns_vector=True)

    def __add__(self, other):
        return self.add(other)

    def __radd__(self, other):
        return self.add(other)

    def __sub__(self, other):
        return self.subtract(other)

    def __rsub__(self, other):
        if _looks_like_iris_vector_operand(other):
            return _coerce_iris_vector_operand(other, self.dtype).subtract(self)
        return _execute_iris_vector_operation("e-", self, other, returns_vector=True)

    def __mul__(self, other):
        return self.multiply(other)

    def __rmul__(self, other):
        return self.multiply(other)

    def __truediv__(self, other):
        return self.divide(other)

    def __rtruediv__(self, other):
        if _looks_like_iris_vector_operand(other):
            return _coerce_iris_vector_operand(other, self.dtype).divide(self)
        return _execute_iris_vector_operation("e/", self, other, returns_vector=True)

    def __neg__(self):
        return _execute_iris_vector_operation("-", self, returns_vector=True)


Vector = IRISVector


def _objectscript_quote(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _vector_cache_root(cache_key: str) -> str:
    return (
        f"^CacheTemp({_objectscript_quote(_VECTOR_CACHE_GLOBAL)},"
        f"{_objectscript_quote(cache_key)}"
    )


def _vector_value_ref(root: str, *names: str) -> str:
    return root + "".join(f",{_objectscript_quote(name)}" for name in names) + ")"


def _build_iris_vector_script(var_name: str, value_ref: str, dtype_ref: str) -> str:
    return (
        f"kill {var_name} "
        f"set data={value_ref},dtype={dtype_ref} "
        f"for i=1:1:$length(data,\",\") "
        f"set item=$piece(data,\",\",i),$vector({var_name},i,dtype)=item"
    )


def _iris_vector_to_string_script(var_name: str, out_ref: str) -> str:
    return (
        f"set out=\"\",{out_ref}=\"\" "
        f"for j=1:1:$vectorop(\"length\",{var_name}) "
        f"set out=out_$select(j=1:\"\",1:\",\")_$vector({var_name},j) "
        f"set {out_ref}=out"
    )


def _execute_iris_vector_operation(
    operation: str,
    left: IRISVector,
    right: Any = None,
    *,
    returns_vector: bool,
):
    try:
        import iris as _iris

        gref = getattr(_iris, "gref")
        execute = getattr(_iris, "execute")
    except Exception as exc:
        raise RuntimeError(
            "IRISVector operations require iris.gref and iris.execute"
        ) from exc

    cache_key = uuid4().hex
    cache = gref("^CacheTemp")
    cache_subscripts = [_VECTOR_CACHE_GLOBAL, cache_key]
    root = _vector_cache_root(cache_key)
    left_values_ref = _vector_value_ref(root, "left", "values")
    left_dtype_ref = _vector_value_ref(root, "left", "dtype")
    right_values_ref = _vector_value_ref(root, "right", "values")
    right_dtype_ref = _vector_value_ref(root, "right", "dtype")
    scalar_ref = _vector_value_ref(root, "right", "scalar")
    out_ref = _vector_value_ref(root, "out")

    try:
        cache.set(cache_subscripts + ["left", "values"], left.to_param())
        cache.set(cache_subscripts + ["left", "dtype"], left._objectscript_dtype)
        execute(_build_iris_vector_script("a", left_values_ref, left_dtype_ref))

        if isinstance(right, IRISVector):
            if right.dtype != left.dtype:
                raise ValueError(
                    f"IRIS VECTOR operations require matching dtypes: {left.dtype!r} != {right.dtype!r}"
                )
            cache.set(cache_subscripts + ["right", "values"], right.to_param())
            cache.set(cache_subscripts + ["right", "dtype"], right._objectscript_dtype)
            execute(_build_iris_vector_script("b", right_values_ref, right_dtype_ref))
            expression = f"$vectorop({_objectscript_quote(operation)},a,b)"
        elif right is None:
            expression = f"$vectorop({_objectscript_quote(operation)},a)"
        else:
            cache.set(
                cache_subscripts + ["right", "scalar"],
                _format_iris_vector_item(right),
            )
            expression = f"$vectorop({_objectscript_quote(operation)},a,{scalar_ref})"

        if returns_vector:
            execute(
                f"set result={expression} "
                + _iris_vector_to_string_script("result", out_ref)
            )
        else:
            execute(f"set {out_ref}={expression}")

        result = cache.get(cache_subscripts + ["out"])
        if returns_vector:
            return IRISVector(result, dtype=left.dtype)
        return result
    finally:
        try:
            cache.kill(cache_subscripts)
        except Exception:
            pass
