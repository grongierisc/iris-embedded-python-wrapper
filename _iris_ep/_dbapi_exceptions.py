from __future__ import annotations

from typing import Any


apilevel = "2.0"
threadsafety = 1
paramstyle = "qmark"


class Warning(Exception):
    """Exception raised for important warnings."""


class Error(Exception):
    """Base class for DB-API exceptions."""


class InterfaceError(Error):
    """Exception raised for interface-related errors."""


class DatabaseError(Error):
    """Exception raised for database-related errors."""


class DataError(DatabaseError):
    pass


class OperationalError(DatabaseError):
    pass


class IntegrityError(DatabaseError):
    pass


class InternalError(DatabaseError):
    pass


class ProgrammingError(DatabaseError):
    pass


class NotSupportedError(DatabaseError):
    pass


def Binary(value: Any):
    return bytes(value)
