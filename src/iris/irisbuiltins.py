from collections import abc

#
# IRIS Exceptions
#
class SQLError(Exception):
    """Error raised on an invalid IRIS SQL statement

    Attributes:
        sqlcode -- IRIS SQL error code
        message -- Error description
        statement -- Statement that failed
    """

    def __init__(self,sqlcode,message,statement=None):
        self.sqlcode = sqlcode
        self.message = message
        self.statement = statement
        super().__init__(self.message)

#
# Helper to raise a properly formatted AttributeError when we decide that
# we don't want to handle a last-chance method.
#
def _no_such_method(target,method):
    raise AttributeError(f"'{target.__class__.__name__}' has no attribute '{method}'")

#
# irisbuiltins:  Implements impedence matching methods for projecting IRIS behavior
#                over Python objects.
#
class irisbuiltins:

    #
    # Common functions for mapping Python collection behavior to IRIS behavior
    #
    # NOTE: With Sequences, the indicies are 0 based for Python and 1 based
    #       for IRIS.
    #
    
    def Count(self):
        if isinstance(self,abc.Mapping) or isinstance(self,abc.Sequence):
           return len(self)
        _no_such_method(self,"Count")

    def GetAt(self,index):
        if isinstance(self,abc.Mapping):
            return self[index]
        if isinstance(self,abc.Sequence):
            return self[index-1]
        _no_such_method(self,"GetAt")

    def SetAt(self,value,index):
        if isinstance(self,abc.Mapping):
            self[index] = value
            return
        if isinstance(self,abc.Sequence):
            self[index-1] = value
            return
        _no_such_method(self,"SetAt")

    def Insert(self,value):
        if isinstance(self,abc.Sequence):
            self.append(value)
            return
        _no_such_method(self,"Insert")

    def InsertAt(self,value,index):
        if isinstance(self,abc.Sequence):
            self.insert(index-1,value)
            return
        _no_such_method(self,"InsertAt")

    def Clear(self):
        if isinstance(self,abc.Mapping) or isinstance(self,abc.Sequence):
           self.clear()
           return
        _no_such_method(self,"Clear")

    def IsDefined(self,key):
        if isinstance(self,abc.Mapping):
            return (key in self)
        _no_such_method(self,"IsDefined")

    def Find(self,value):
        if isinstance(self,abc.Sequence):
            return self.index(value)+1
        if isinstance(self,abc.Mapping):
            for (k,v) in self.items():
                if v == value:
                    return k
            return None;
        _no_such_method(self,"Find")

#
# End-of-file
#
