from typing import Any, Optional
from dataclasses import dataclass

@dataclass
class PreparedQuery:
    def execute(self, **kwargs) -> Any:
        """
        Execute a prepared query, you can pass values
        """
        ...

@dataclass
class SQLMethods:
    def exec(self, query: str) -> Any:
        """
        Execute a query
        """
        ...
    
    def prepare(self, query: str) -> PreparedQuery:
        """
        Prepare a query
        """
        ...

def check_status(status: Any) -> None:
    """
    Raises an exception if status contains an error.
    Returns None if no error condition occurs.
    """
    ...

def cls(class_name: str) -> Any:
    """
    Returns a reference to an InterSystems IRIS class. This allows you access the
    properties and methods of that class in the same way you would a with a Python
    class. You can use iris.cls() to access both built-in InterSystems IRIS classes
    or custom InterSystems IRIS classes you write yourself.
    """
    ...

def execute(statement: str) -> Optional[Any]:
    """
    Executes an ObjectScript statement and optionally returns a value.
    """
    ...

def gref(global_name: str) -> Any:
    """
    Returns a reference to an InterSystems IRIS global. The global may or may
    not already exist.
    """
    ...

def lock(lock_list: list[str], timeout_value: int = None, locktype: str = None) -> bool:
    """
    Sets locks, given a list of lock names, an optional timeout value (in seconds),
    and an optional lock type. If locktype is "S", this indicates a shared lock.\n
    In InterSystems IRIS, a lock is used to prevent more than one user or process
    from accessing or modifying the same resource (usually a global) at the same
    time. For example, a process that writes to a resource should request an exclusive
    lock (the default) so that another process does not attempt to read or write to that
    resource simultaneously. A process that reads a resource can request a shared lock so
    that other processes can read that resource at the same time, but not write to that
    resource. A process can specify a timeout value, so that it does not wait forever
    waiting for a resource to become available.
    """
    ...

def ref(value: Any) -> Any:
    """
    Creates an iris.ref object with a specified value. This is useful for
    situations when you need to pass an argument to an ObjectScript method by reference.
    """
    ...

def routine(routine_name: str, **kwargs) -> Any:
    """
    Invokes an InterSystems IRIS routine, optionally at a given tag. Any arguments
    that need to be passed in the call are comma-delimited, following the name of
    the routine.
    """
    ...

def tcommit():
    """
    Marks the successful end of an InterSystems IRIS transaction.
    """
    ...

def tlevel():
    """
    Detects whether a transaction is currently in progress and returns the
    nesting level. A call to iris.tstart() increments the nesting level, and a
    call to iris.tcommit() decrements the nesting level. A value of zero means not
    in a transaction.
    """
    ...

def trollback():
    """
    Rolls back all current transactions in progress and restores all journaled
    database values to their values at the start of the initial transaction. It
    also resets the transaction nesting level to 0.
    """
    ...

def trollbackone():
    """
    Rolls back the current level of nested transactions, that is, the one initiated
    by the most recent iris.tstart(). It also decrements the transaction nesting
    level by 1.
    """
    ...

def tstart():
    """
    Marks the start of an InterSystems IRIS transaction.\n
    A transaction is a group of commands that must all complete in order for
    the transaction to be considered successful. For example, if you have a
    transaction that transfers a sum of money from one bank account to another,
    the transaction is only successful if withdrawing the money from the first
    account and depositing it into the second account are both successful. If
    the transaction fails, the database can be rolled back to the state it was
    in before the start of the transaction.
    """
    ...

def unlock(lock_list: list[str], timeout_value: int = None, locktype: str = None) -> bool:
    """
    Removes locks, given a list of lock names, an optional timeout value
    (in seconds), and an optional lock type.\n
    If your code sets locks to control access to resources, it should unlock
    them when it is done using those resources.
    """
    ...

sql: SQLMethods = ...
