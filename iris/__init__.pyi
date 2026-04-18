from __future__ import annotations

import os
from typing import Any, Iterator, List, Optional, Tuple

from . import iris_ipm

__all__ = [
    'check_status', 'cls', 'connect', 'createConnection', 'createIRIS', 'dbapi', 'execute', 'gref', 'iris_ipm',
    'lock', 'os', 'ref', 'routine', 'runtime', 'sql', 'system',
    'tcommit', 'tlevel', 'trollback', 'trollbackone', 'tstart', 'unlock', 'utils',
]

# Native API connection helpers

class IRISConnection:
    """
    Represents an open connection to an InterSystems IRIS instance (Native API).
    Returned by createConnection().
    """
    def close(self) -> None:
        """Close the connection."""
    def isConnected(self) -> bool:
        """Return True if the connection is still open."""

class IRIS:
    """
    The InterSystems IRIS Native API object.
    Returned by createIRIS(). Bind it into iris.runtime when native mode is needed.
    """
    def classMethodValue(self, class_name: str, method_name: str, *args: Any) -> Any:
        """Invoke a class method and return its value."""
    def classMethodVoid(self, class_name: str, method_name: str, *args: Any) -> None:
        """Invoke a class method that returns no value."""
    def invokeClassMethod(self, class_name: str, method_name: str, *args: Any) -> Any:
        """Invoke a class method and return its value (legacy API)."""
    def invoke(self, oref: Any, method_name: str, *args: Any) -> Any:
        """Invoke an instance method on an IRISObject."""
    def get(self, oref: Any, prop_name: str) -> Any:
        """Get a property value from an IRISObject."""
    def set(self, oref: Any, prop_name: str, value: Any) -> None:
        """Set a property value on an IRISObject."""
    def lock(self, lock_reference: str, timeout: int = ..., lock_type: str = ...) -> bool:
        """Acquire a lock on an IRIS resource."""
    def unlock(self, lock_reference: str, lock_type: str = ...) -> None:
        """Release a lock on an IRIS resource."""
    def iterator(self, global_name: str, *subscripts: Any) -> Iterator[Any]:
        """Return an iterator over subscripts of a global node."""

def connect(
    hostname: str,
    port: int,
    namespace: str,
    username: str,
    password: str,
    timeout: Optional[int] = ...,
    sharedmemory: bool = ...,
    logfile: Optional[str] = ...,
) -> IRISConnection:
    """
    Open a connection to an InterSystems IRIS instance using the Native API.
    Returns an IRISConnection that must be passed to createIRIS().
    Example: conn = iris.connect("localhost", 1972, "USER", "_SYSTEM", "SYS")
    """

def createConnection(
    hostname: str,
    port: int,
    namespace: str,
    username: str,
    password: str,
    timeout: Optional[int] = ...,
    sharedmemory: bool = ...,
    logfile: Optional[str] = ...,
) -> IRISConnection:
    """
    Open a connection to an InterSystems IRIS instance using the Native API.
    Returns an IRISConnection that must be passed to createIRIS().
    Example: conn = iris.createConnection("localhost", 1972, "USER", "_SYSTEM", "SYS")
    """

def createIRIS(conn: IRISConnection) -> IRIS:
    """
    Create an IRIS Native API object from an open connection.
    The returned IRIS object can be bound through iris.runtime.configure(mode="native", iris=db).
    Example: db = iris.createIRIS(conn); iris.runtime.configure(mode="native", iris=db)
    """

# Module-level functions

def check_status(status: Any) -> None:
    """
    Raises an exception on an error status, or returns None if no error condition occurs.
    Example: iris.check_status(st) checks the status code st to see if it contains an error.
    """

def cls(class_name: str) -> Any:
    """
    Returns a reference to an InterSystems IRIS class.
    Example: iris.cls("%SYSTEM.INetInfo").LocalHostName() calls a method in the class %SYSTEM.INetInfo.
    """

def execute(statements: str) -> None:
    """
    Execute IRIS ObjectScript statements.
    Example: iris.execute("set x=\\"Hello\\"\\nw x,!\\n") returns nothing.
    """

def gref(global_name: str) -> global_ref:
    """
    Returns a reference to an InterSystems IRIS global.
    Example: g = iris.gref("^foo") sets g to a reference to global ^foo
    """

def lock(
    lock_list: List[str],
    timeout_value: Optional[int] = ...,
    locktype: Optional[str] = ...,
) -> None:
    """
    Sets locks, given a list of lock names, an optional timeout value (in seconds), and an optional locktype.
    Example: iris.lock(["^foo","^bar"], 30, "S") sets locks "^foo" and "^bar", waiting up to 30 seconds, and using shared locks.
    """

def routine(routine: str, *args: Any) -> Any:
    """
    Invokes an InterSystems IRIS routine, optionally at a given tag.
    Example: iris.routine("Stop^SystemPerformance", "20211221_160620_test") calls tag Stop in routine ^SystemPerformance.
    """

def tcommit() -> None:
    """
    Marks a successful end of an InterSystems IRIS transaction.
    Example: iris.tcommit() marks the successful end of a transaction and decrements the nesting level by 1.
    """

def tlevel() -> int:
    """
    Detects whether a transaction is currently in progress and returns the nesting level.
    Zero means not in a transaction.
    Example: iris.tlevel() returns the current transaction nesting level, or zero if not in a transaction.
    """

def trollback() -> None:
    """
    Terminates the current transaction and restores all journaled database values to their values at the start of the transaction.
    Example: iris.trollback() rolls back all current transactions in progress and resets the transaction nesting level to 0.
    """

def trollbackone() -> None:
    """
    Rolls back the current level of nested transactions, that is, the one initiated by the most recent tstart().
    Example: iris.trollbackone() rolls back the current level of nested transactions and decrements the nesting level by 1.
    """

def tstart() -> None:
    """
    Starts an InterSystems IRIS transaction.
    Example: iris.tstart() marks the beginning of a transaction.
    """

def unlock(
    lock_list: List[str],
    timeout_value: Optional[int] = ...,
    locktype: Optional[str] = ...,
) -> None:
    """
    Removes locks, given a list of lock names, an optional timeout value (in seconds), and an optional locktype.
    Example: iris.unlock(["^foo","^bar"], 30, "S") removes locks "^foo" and "^bar", waiting up to 30 seconds, and using shared locks.
    """

def utils() -> Any:
    """
    Returns a reference to the InterSystems IRIS utilities class.
    Example: iris.utils().$Job() returns the current job number.
    """

class RuntimeContext:
    mode: str
    state: str
    install_dir: Optional[str]
    embedded_available: bool
    iris: Optional[IRIS]
    dbapi: Any
    native_connection: Optional[IRISConnection]

class Runtime:
    @property
    def state(self) -> str: ...
    @property
    def mode(self) -> str: ...
    @property
    def embedded_available(self) -> bool: ...
    @property
    def iris(self) -> Optional[IRIS]: ...
    @property
    def dbapi(self) -> Any: ...
    @property
    def native_connection(self) -> Optional[IRISConnection]: ...
    def get(self) -> RuntimeContext: ...
    def configure(
        self,
        mode: str = ...,
        install_dir: Optional[str] = ...,
        iris: Optional[IRIS] = ...,
        dbapi: Any = ...,
        native_connection: Optional[IRISConnection] = ...,
    ) -> RuntimeContext: ...
    def reset(self) -> RuntimeContext: ...

runtime: Runtime

# By-reference container

class ref:
    """
    A by-reference container for passing output parameters to InterSystems IRIS methods.
    Example: iris.ref("hello") creates an iris.ref object with the value "hello".
    """
    value: Any
    def __init__(self, value: Any = ...) -> None: ...

# Global reference

class global_ref:
    """Reference to an InterSystems IRIS global variable."""

    def data(self, key: Optional[List[Any]] = ...) -> int:
        """
        Checks if a node of a global contains data and/or has descendants.
        The key of the node is passed as a list; None or [] indicates the root node.
        Returns 0 (undefined), 1 (defined), 10 (undefined with descendants), or 11 (defined with descendants).
        """
    def get(self, key: Optional[List[Any]] = ...) -> Any:
        """
        Gets the value stored at a node of a global.
        The key of the node is passed as a list; None or [] indicates the root node.
        """
    def getAsBytes(self, key: Optional[List[Any]] = ...) -> bytes:
        """
        Gets a string value stored at a node of a global and converts it to the Python bytes type.
        The key of the node is passed as a list; None or [] indicates the root node.
        """
    def keys(self, key: List[Any] = ...) -> Iterator[Any]:
        """
        Returns the keys of a global starting from a given key.
        The starting key is passed as a list; [] indicates the root node.
        """
    def kill(self, key: Optional[List[Any]] = ...) -> None:
        """
        Deletes the node of a global (and all its descendants), if it exists.
        The key is passed as a list; None or [] indicates the root node.
        """
    def order(self, key: List[Any]) -> Optional[Any]:
        """
        Returns the next sibling key at the same level of the global, starting from the given key.
        Returns None if no key follows.
        """
    def orderiter(self, key: List[Any] = ...) -> Iterator[Tuple[Any, Any]]:
        """
        Iterates keys and values of a global from the given key down to the next leaf node.
        Yields (key, value) tuples.
        """
    def query(self, key: List[Any] = ...) -> Iterator[Tuple[Any, Any]]:
        """
        Traverses a global starting at the given key, yielding (key, value) tuples for each node.
        """
    def set(self, key: Optional[List[Any]], value: Any) -> None:
        """
        Sets a node in a global to a given value.
        The key is passed as a list; None or [] indicates the root node.
        """

# SQL API

class _SQLResult:
    """Result set returned by sql.exec() or PreparedQuery.execute()."""
    description: Any
    rowcount: int
    def __iter__(self) -> Iterator[Any]: ...
    def __next__(self) -> Any: ...

class _PreparedQuery:
    """Prepared SQL statement returned by sql.prepare()."""
    def execute(self, *args: Any, **kwargs: Any) -> _SQLResult:
        """Execute the prepared query, optionally passing parameter values."""

class _SQL:
    """Provides access to the InterSystems IRIS SQL API."""
    def exec(self, query: str) -> _SQLResult:
        """Execute a SQL query and return the result set."""
    def prepare(self, query: str) -> _PreparedQuery:
        """Prepare a SQL query for repeated or parameterised execution."""

sql: _SQL

class _DBAPICursor:
    arraysize: int
    description: Any
    rowcount: int
    def execute(self, operation: str, params: Optional[Any] = ...) -> _DBAPICursor: ...
    def fetchone(self) -> Optional[Any]: ...
    def fetchmany(self, size: Optional[int] = ...) -> List[Any]: ...
    def fetchall(self) -> List[Any]: ...
    def close(self) -> None: ...

class _DBAPIConnection:
    def cursor(self) -> _DBAPICursor: ...
    def close(self) -> None: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...

class _DBAPI:
    apilevel: str
    threadsafety: int
    paramstyle: str
    Warning: Any
    Error: Any
    InterfaceError: Any
    DatabaseError: Any
    DataError: Any
    OperationalError: Any
    IntegrityError: Any
    InternalError: Any
    ProgrammingError: Any
    NotSupportedError: Any
    def connect(self, *args: Any, mode: str = ..., **kwargs: Any) -> Any: ...

dbapi: _DBAPI

# System API

class _DocDB:
    """Provides access to the InterSystems IRIS Document Database API."""
    def CreateDatabase(self, name: str, path: str, **kwargs: Any) -> Any:
        """Create a new document database."""
    def DropAllDatabases(self) -> Any:
        """Drop all document databases."""
    def DropDatabase(self, name: str) -> Any:
        """Drop a named document database."""
    def Exists(self, name: str) -> bool:
        """Return True if the named document database exists."""
    def GetAllDatabases(self) -> Any:
        """Return all document databases."""
    def GetDatabase(self, name: str) -> Any:
        """Return the named document database."""
    def Help(self) -> None:
        """Print help information."""

class _System:
    """
    Provides access to the InterSystems IRIS system API.
    Available sub-namespaces: DocDB, Encryption, Error, Event, Monitor,
    Process, Python, SQL, SYS, Security, Semaphore, Status, Util, Version.
    """
    DocDB: _DocDB
    class Encryption:
        """Provides access to the InterSystems IRIS Encryption API."""
    class Error:
        """Provides access to the InterSystems IRIS Error API."""
    class Event:
        """Provides access to the InterSystems IRIS Event API."""
    class Monitor:
        """Provides access to the InterSystems IRIS Monitor API."""
    class Process:
        """Provides access to the InterSystems IRIS Process API."""
    class Python:
        """Provides access to the InterSystems IRIS Python API."""
    class SQL:
        """Provides access to the InterSystems IRIS SQL system API."""
    class SYS:
        """Provides access to the InterSystems IRIS SYS API."""
    class Security:
        """Provides access to the InterSystems IRIS Security API."""
    class Semaphore:
        """Provides access to the InterSystems IRIS Semaphore API."""
    class Status:
        """Provides access to the InterSystems IRIS Status API."""
    class Util:
        """Provides access to the InterSystems IRIS Util API."""
    class Version:
        """Provides access to the InterSystems IRIS Version API."""

system: _System

