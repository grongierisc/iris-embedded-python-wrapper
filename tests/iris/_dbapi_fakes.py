class FakeStatementResult:
    def __init__(self, rows):
        self._rows = rows
        self._index = -1
        self._column_count = len(rows[0]) if rows else 0

    def _Next(self):
        self._index += 1
        return self._index < len(self._rows)

    def _GetData(self, index):
        return self._rows[self._index][index - 1]

    def _Get(self, index):
        return self._GetData(index)

    def _GetColumnCount(self):
        return self._column_count


class FakeStatementResultNoColumnCount:
    def __init__(self, rows):
        self._rows = rows
        self._index = -1

    def _Next(self):
        self._index += 1
        return self._index < len(self._rows)

    def _GetData(self, index):
        row = self._rows[self._index]
        if index < 1 or index > len(row):
            raise IndexError(index)
        return row[index - 1]

    def _Get(self, index):
        return self._GetData(index)


class FakeStatementResultNoColumnCountInfinite:
    def __init__(self):
        self._seen = 0

    def _Next(self):
        # Single row shape for test purposes.
        self._seen += 1
        return self._seen == 1

    def _GetData(self, index):
        # Never raises, which previously caused an infinite loop.
        return index

    def _Get(self, index):
        return self._GetData(index)


class FakeStatementResultGetDataOnly:
    def __init__(self, rows):
        self._rows = rows
        self._index = -1
        self._column_count = len(rows[0]) if rows else 0

    def _Next(self):
        self._index += 1
        return self._index < len(self._rows)

    def _GetData(self, index):
        return self._rows[self._index][index - 1]

    def _GetColumnCount(self):
        return self._column_count


class FakeStatementResultAttrOnly:
    def __init__(self, rows, columns):
        self._rows = rows
        self._columns = columns
        self._index = -1

    def _Next(self):
        self._index += 1
        if self._index >= len(self._rows):
            return False

        row = self._rows[self._index]
        for name, value in zip(self._columns, row):
            setattr(self, name, value)
            setattr(self, name.upper(), value)
        return True


class FakeStatement:
    def __init__(self, rows):
        self.rows = rows
        self.prepare_seen = None
        self.execute_args = None
        self.execute_kwargs = None

    def _Prepare(self, query):
        self.prepare_seen = query
        return 1

    def _Execute(self, *args, **kwargs):
        self.execute_args = args
        self.execute_kwargs = kwargs
        return FakeStatementResult(self.rows)


class FakeStatementNoColumnCount(FakeStatement):
    def _Execute(self, *args, **kwargs):
        self.execute_args = args
        self.execute_kwargs = kwargs
        return FakeStatementResultNoColumnCount(self.rows)


class FakeStatementNoColumnCountInfinite(FakeStatement):
    def _Execute(self, *args, **kwargs):
        self.execute_args = args
        self.execute_kwargs = kwargs
        return FakeStatementResultNoColumnCountInfinite()


class FakeStatementGetDataOnly(FakeStatement):
    def _Execute(self, *args, **kwargs):
        self.execute_args = args
        self.execute_kwargs = kwargs
        return FakeStatementResultGetDataOnly(self.rows)


class FakeStatementAttrOnly(FakeStatement):
    def __init__(self, rows, columns):
        super().__init__(rows)
        self.columns = columns

    def _Execute(self, *args, **kwargs):
        self.execute_args = args
        self.execute_kwargs = kwargs
        return FakeStatementResultAttrOnly(self.rows, self.columns)


class FakeStatementFactory:
    def __init__(self, statement):
        self.statement = statement

    def _New(self):
        return self.statement


class FakeNamespaceProcess:
    def __init__(self, namespace="BASE"):
        self.namespace = namespace
        self.calls = []

    def NameSpace(self):
        self.calls.append(("NameSpace", self.namespace))
        return self.namespace

    def SetNamespace(self, namespace):
        self.calls.append(("SetNamespace", namespace))
        self.namespace = namespace
        return namespace


class FakeNamespaceStatementResult:
    def __init__(self, process):
        self.process = process
        self._seen = False

    def _Next(self):
        if self._seen:
            return False
        self._seen = True
        return True

    def _GetData(self, index):
        assert index == 1
        return self.process.namespace


class FakeNamespaceStatement:
    def __init__(self, process):
        self.process = process
        self.prepare_seen = None
        self.execute_namespaces = []

    def _Prepare(self, query):
        self.prepare_seen = query
        return 1

    def _Execute(self, *args, **kwargs):
        self.execute_namespaces.append(self.process.namespace)
        return FakeNamespaceStatementResult(self.process)


class FakeNamespaceStatementFactory:
    def __init__(self, process):
        self.process = process
        self.statements = []

    def _New(self):
        statement = FakeNamespaceStatement(self.process)
        self.statements.append(statement)
        return statement
