from __future__ import annotations
from typing import Any
from iris.iris_ipm import ipm
from . import iris_ipm
__all__ = [ 'check_status', 'cls', 'execute', 'gref', 'ipm', 'iris_ipm', 'lock', 'os', 'ref', 'routine', 'sql', 'system', 'tcommit', 'tlevel', 'trollback', 'trollbackone', 'tstart', 'unlock', 'utils']
def check_status(self, status):
    """
    Raises an exception on an error status, or returns None if no error condition occurs.
    Example: iris.check_status(st) checks the status code st to see if it contains an error.
    """
def cls(self, class_name):
    """
    Returns a reference to an InterSystems IRIS class.
    Example: iris.cls("%SYSTEM.INetInfo").LocalHostName() calls a method in the class %SYSTEM.INetInfo.
    """
def execute(self, statements):
    """
    execute IRIS statements.
    Example: iris.execute("set x="Hello"\nw x,!\n") returns nothing.
    """
def gref(self, global_name):
    """
    Returns a reference to an InterSystems IRIS global.
    Example: g = iris.gref("^foo") sets g to a reference to global ^foo
    """
def lock(self, lock_list, timeout_value, locktype):
    """
    Sets locks, given a list of lock names, an optional timeout value (in seconds), and an optional locktype.
    Example: iris.lock(["^foo","^bar"], 30, "S") sets locks "^foo" and "^bar", waiting up to 30 seconds, and using shared locks.
    """
def ref(self, value):
    """
    Creates an iris.ref object with a specified value.
    Example: iris.ref("hello") creates an iris.ref object with the value "hello"
    """
def routine(self, routine, args):
    """
    Invokes an InterSystems IRIS routine, optionally at a given tag.
    Example: iris.routine("Stop^SystemPerformance", "20211221_160620_test") calls tag Stop in routine ^SystemPerformance.
    """
def tcommit(self):
    """
    Marks a successful end of an InterSystems IRIS transaction.
    Example: iris.commit() marks the successful end of a transaction and decrements the nesting level by 1
    """
def tlevel(self):
    """
    Detects whether a transaction is currently in progress and returns the nesting level. Zero means not in a transaction.
    Example: iris.tlevel() returns the current transaction nesting level, or zero if not in a transaction
    """
def trollback(self):
    """
    Terminates the current transaction and restores all journaled database values to their values at the start of the transaction.
    Example: iris.trollback() rolls back all current transactions in progress and resets the transaction nesting level to 0
    """
def trollbackone(self):
    """
    Rolls back the current level of nested transactions, that is, the one initiated by the most recent tstart().
    Example: iris.trollbackone() rolls back the current level of nested transactions and decrements the nesting level by 1
    """
def tstart(self):
    """
    Starts an InterSystems IRIS transaction.
    Example: iris.tstart() marks the beginning of a transaction.
    """
def unlock(self, lock_list, timout_value, locktype):
    """
    Removes locks, given a list of lock names, an optional timeout value (in seconds), and an optional locktype.
    Example: iris.unlock(["^foo","^bar"], 30, "S") removes locks "^foo" and "^bar", waiting up to 30 seconds, and using shared locks.
    """
def utils(self):
    """
    Returns a reference to the InterSystems IRIS utilities class.
    Example: iris.utils().$Job() returns the current job number.
    """
# stubs for the sql object
class sql:
    """
    The sql object provides access to the InterSystems IRIS SQL API.
    """
    def exec(self, query: str) -> Any:
        """
        Execute a query
        """
    def prepare(self, query: str) -> PreparedQuery:
        """
        Prepare a query
        """
    class PreparedQuery:
        def execute(self, **kwargs) -> Any:
            """
            Execute a prepared query, you can pass values
            """
# stubs for the system object
class system:
    """
    The system object provides access to the InterSystems IRIS system API.
    The following classes are available:
    'DocDB', 'Encryption', 'Error', 'Event', 'Monitor', 'Process', 'Python', 'SQL', 'SYS', 'Security', 'Semaphore', 'Status', 'Util', 'Version'
    """
    class DocDB:
        """
        The DocDB class provides access to the InterSystems IRIS Document Database API.
        The following methods are available:
        'CreateDatabase', 'DropAllDatabases', 'DropDatabase', 'Exists', 'GetAllDatabases', 'GetDatabase', 'Help'
        """
        def CreateDatabase(self, name: str, path: str, **kwargs) -> Any:
            """
            Create a database
            """
        def DropAllDatabases(self) -> Any:
            """
            Drop all databases
            """
        def DropDatabase(self, name: str) -> Any:
            """
            Drop a database
            """
        def Exists(self, name: str) -> Any:
            """
            Check if a database exists
            """
        def GetAllDatabases(self) -> Any:
            """
            Get all databases
            """
        def GetDatabase(self, name: str) -> Any:
            """
            Get a database
            """
        def Help(self) -> Any:
            """
            Get help
            """
    def Encryption(self) -> Any:
        """
        The Encryption class provides access to the InterSystems IRIS Encryption API.
        """
    def Error(self) -> Any:
        """
        The Error class provides access to the InterSystems IRIS Error API.
        """
    def Event(self) -> Any:
        """
        The Event class provides access to the InterSystems IRIS Event API.
        """
    def Monitor(self) -> Any:
        """
        The Monitor class provides access to the InterSystems IRIS Monitor API.
        """
    def Process(self) -> Any:
        """
        The Process class provides access to the InterSystems IRIS Process API.
        """
    def Python(self) -> Any:
        """
        The Python class provides access to the InterSystems IRIS Python API.
        """
    def SQL(self) -> Any:
        """
        The SQL class provides access to the InterSystems IRIS SQL API.
        """
    def SYS(self) -> Any:
        """
        The SYS class provides access to the InterSystems IRIS SYS API.
        """
    def Security(self) -> Any:
        """
        The Security class provides access to the InterSystems IRIS Security API.
        """
    def Semaphore(self) -> Any:
        """
        The Semaphore class provides access to the InterSystems IRIS Semaphore API.
        """
    def Status(self) -> Any:
        """
        The Status class provides access to the InterSystems IRIS Status API.
        """
    def Util(self) -> Any:
        """
        The Util class provides access to the InterSystems IRIS Util API.
        """
    def Version(self) -> Any:
        """
        The Version class provides access to the InterSystems IRIS Version API.
        """

