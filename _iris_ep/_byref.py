from __future__ import annotations

from typing import Any


class ByRef:
    """Small by-reference container compatible with embedded IRIS output args."""

    def __init__(self, value: Any = "", type: Any = None):
        self.value = value
        self.type = type


def make_ref(value: Any = ""):
    try:
        import iris as _iris

        ref_factory = getattr(_iris, "ref", None)
        if callable(ref_factory):
            return ref_factory(value)
    except Exception:
        pass

    return ByRef(value)
