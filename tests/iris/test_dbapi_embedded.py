from decimal import Decimal
import pytest
import iris as public_iris
import iris_embedded_python as iris
import _iris_ep
import _iris_ep._dbapi_embedded as embedded_dbapi
import _iris_ep._vector as vector_module
import sys
import types

from tests.iris._dbapi_fakes import (
    FakeStatement,
    FakeStatementAttrOnly,
    FakeStatementFactory,
    FakeStatementGetDataOnly,
    FakeStatementNoColumnCount,
    FakeStatementNoColumnCountInfinite,
)


class FakeIRISStream:
    def __init__(self, class_name, content):
        self.class_name = class_name
        self.content = content
        self.rewound = False

    def invoke(self, method_name, *args):
        if method_name == "%ClassName":
            return self.class_name
        if method_name == "Rewind":
            self.rewound = True
            return None
        if method_name == "Read":
            return self.content
        raise AttributeError(method_name)

    def get(self, property_name):
        if property_name == "Size":
            return len(self.content)
        raise AttributeError(property_name)


class FakeStreamGlobal:
    def __init__(self, values):
        self.values = values

    def get(self, key):
        return self.values.get(tuple(str(part) for part in key))


class FakeStatementResultWithRowcount:
    def __init__(self, rowcount):
        self._ROWCOUNT = rowcount


class FakeStatementWithRowcount(FakeStatement):
    def __init__(self, rowcounts):
        super().__init__([])
        self.rowcounts = list(rowcounts)

    def _Execute(self, *args, **kwargs):
        self.execute_args = args
        self.execute_kwargs = kwargs
        rowcount = self.rowcounts.pop(0)
        return FakeStatementResultWithRowcount(rowcount)


class FakeMetadataColumn:
    def __init__(
        self,
        label,
        client_type=10,
        runtime_type=None,
        sql_category=None,
        is_expression=0,
        precision=10,
    ):
        self.label = label
        self.colName = label
        self.clientType = client_type
        self.isExpression = is_expression
        self.precision = precision
        self.property = types.SimpleNamespace(RuntimeType=runtime_type, Type=runtime_type)
        self.typeClass = types.SimpleNamespace(Name=runtime_type, SqlCategory=sql_category)


class FakeMetadataColumns:
    def __init__(self, columns):
        self._columns = columns

    def GetAt(self, index):
        return self._columns[index - 1]


class FakeMetadata:
    def __init__(self, columns):
        self.columns = FakeMetadataColumns(columns)
        self.columnCount = len(columns)


class FakeVectorStatementResult:
    def __init__(self, rows, columns):
        self._rows = rows
        self._columns = columns
        self._index = -1
        self._ResultColumnCount = len(columns)

    def _GetMetadata(self):
        return FakeMetadata(self._columns)

    def _Next(self):
        self._index += 1
        return self._index < len(self._rows)

    def _GetData(self, index):
        column = self._columns[index - 1]
        if getattr(column.property, "RuntimeType", None) == "%Library.Vector":
            raise TypeError("Unsupported type")
        return self._rows[self._index][index - 1]

    def _GetRow(self, row_ref):
        self._index += 1
        if self._index >= len(self._rows):
            return 0
        row_ref.value = self._rows[self._index]
        return 1


class FakeVectorStatement(FakeStatement):
    def __init__(self, rows, columns):
        super().__init__(rows)
        self.columns = columns

    def _Execute(self, *args, **kwargs):
        self.execute_args = args
        self.execute_kwargs = kwargs
        return FakeVectorStatementResult(self.rows, self.columns)


def test_public_byref_helper(monkeypatch):
    assert iris.ByRef is public_iris.ByRef
    assert not hasattr(iris.dbapi, "ByRef")
    assert not hasattr(iris.dbapi, "make_ref")
    assert not hasattr(iris.dbapi, "IRISList")
    assert not hasattr(iris.dbapi, "IRISVector")
    assert not hasattr(iris.dbapi, "Vector")

    ref = public_iris.ByRef("start")
    assert ref.value == "start"
    ref.value = "done"
    assert ref.value == "done"

    monkeypatch.setitem(sys.modules, "iris", types.SimpleNamespace())
    fallback_ref = public_iris.make_ref("fallback")
    assert isinstance(fallback_ref, public_iris.ByRef)
    assert fallback_ref.value == "fallback"


def test_public_make_ref_uses_runtime_ref(monkeypatch):
    class FakeRef:
        def __init__(self, value=""):
            self.value = value

    monkeypatch.setitem(sys.modules, "iris", types.SimpleNamespace(ref=FakeRef))

    ref = public_iris.make_ref("native")

    assert isinstance(ref, FakeRef)
    assert ref.value == "native"


def test_dbapi_vector_normalizes_as_embedded_param():
    assert iris.Vector is public_iris.Vector
    assert iris.IRISVector is public_iris.IRISVector
    assert public_iris.Vector is public_iris.IRISVector

    vector = public_iris.Vector([1, "2.5", Decimal("3.0")])

    assert isinstance(vector, public_iris.IRISVector)
    assert list(vector) == [Decimal("1"), Decimal("2.5"), Decimal("3.0")]
    assert vector.to_param() == "1,2.5,3.0"
    assert str(vector) == "1,2.5,3.0"
    assert vector.to_json_array() == "[1,2.5,3.0]"
    assert vector.to_sql() == "TO_VECTOR(?, decimal)"
    assert embedded_dbapi._normalize_embedded_params((vector,)) == ("1,2.5,3.0",)
    assert embedded_dbapi._normalize_embedded_params({"v": vector}) == {
        "v": "1,2.5,3.0"
    }


def test_dbapi_iris_list_normalizes_as_embedded_param():
    assert iris.IRISList is public_iris.IRISList
    assert not hasattr(iris.dbapi, "IRISList")

    payload = public_iris.IRISList([1, "two", Decimal("3.5"), None])
    payload_bytes = payload.to_param()

    assert isinstance(payload, public_iris.IRISList)
    assert len(payload) == 4
    assert payload.count() == 4
    assert payload[0] == 1
    assert payload[-1] is None
    assert list(payload) == [1, "two", Decimal("3.5"), None]
    assert isinstance(payload_bytes, bytes)

    copy = public_iris.IRISList.from_db(payload_bytes)
    assert copy == payload
    assert list(copy) == [1, "two", Decimal("3.5"), None]

    nested = public_iris.IRISList([payload])
    nested_value = nested.getIRISList(1)
    assert isinstance(nested_value, public_iris.IRISList)
    assert list(nested_value) == [1, "two", Decimal("3.5"), None]

    assert embedded_dbapi._normalize_embedded_params((payload,)) == (payload_bytes,)
    assert embedded_dbapi._normalize_embedded_params({"payload": payload}) == {
        "payload": payload_bytes
    }


def test_dbapi_vector_parses_fetched_string_and_int_dtype():
    vector = public_iris.Vector.from_db("[1,2,3]", dtype="int")

    assert list(vector) == [1, 2, 3]
    assert vector.dtype == "integer"
    assert vector.to_param() == "1,2,3"
    assert vector.to_sql(":embedding") == "TO_VECTOR(:embedding, integer)"

    float_vector = public_iris.Vector([1, 2, 3], dtype="float")
    assert float_vector.dtype == "float"
    assert list(float_vector) == [1.0, 2.0, 3.0]
    assert float_vector.to_sql(":embedding") == "TO_VECTOR(:embedding, float)"


def test_dbapi_vector_operations_delegate_to_iris_vectorop(monkeypatch):
    calls = []

    def fake_execute(operation, left, right=None, *, returns_vector):
        calls.append(
            (
                operation,
                left.to_param(),
                getattr(right, "to_param", lambda: right)(),
                returns_vector,
            )
        )
        if returns_vector:
            return public_iris.Vector([9, 9, 9], dtype=left.dtype)
        return {
            "sum": 6,
            "dot-product": 32,
            "cosine-similarity": 1,
        }[operation]

    monkeypatch.setattr(vector_module, "_execute_iris_vector_operation", fake_execute)

    vector = public_iris.Vector([1, 2, 3])

    assert vector.sum() == 6
    assert vector.dot([4, 5, 6]) == 32
    assert vector.cosine(public_iris.Vector([1, 2, 3])) == 1
    assert vector.add([4, 5, 6]).to_param() == "9,9,9"
    assert vector.add(2).to_param() == "9,9,9"

    assert calls == [
        ("sum", "1,2,3", None, False),
        ("dot-product", "1,2,3", "4,5,6", False),
        ("cosine-similarity", "1,2,3", "1,2,3", False),
        ("v+", "1,2,3", "4,5,6", True),
        ("+", "1,2,3", 2, True),
    ]


def test_dbapi_embedded_execute_and_fetch(monkeypatch):
    fake_statement = FakeStatement([(10, "x"), (20, "y")])

    def fake_cls(name):
        assert name == "%SQL.Statement"
        return FakeStatementFactory(fake_statement)

    monkeypatch.setattr(_iris_ep, "cls", fake_cls, raising=False)
    monkeypatch.setattr(
        _iris_ep.dbapi._runtime_manager,
        "get",
        lambda: types.SimpleNamespace(
            embedded_available=True,
            state="embedded-kernel",
            dbapi=None,
        ),
    )

    conn = iris.dbapi.connect(mode="embedded")
    cur = conn.cursor()

    cur.execute("select * from Demo")
    assert fake_statement.prepare_seen == "select * from Demo"
    assert cur.description == (
        ("1", None, None, None, None, None, None),
        ("2", None, None, None, None, None, None),
    )
    assert cur.rowcount == -1
    assert cur.fetchone() == (10, "x")
    assert cur.fetchmany(1) == [(20, "y")]
    assert cur.fetchall() == []

    cur.close()
    conn.close()


def test_dbapi_embedded_normalizes_sql_null_and_empty_string(monkeypatch):
    fake_statement = FakeStatement([("", "\x00", "plain", None)])

    def fake_cls(name):
        assert name == "%SQL.Statement"
        return FakeStatementFactory(fake_statement)

    monkeypatch.setattr(_iris_ep, "cls", fake_cls, raising=False)
    monkeypatch.setattr(
        _iris_ep.dbapi._runtime_manager,
        "get",
        lambda: types.SimpleNamespace(
            embedded_available=True,
            state="embedded-kernel",
            dbapi=None,
        ),
    )

    conn = iris.dbapi.connect(mode="embedded")
    cur = conn.cursor()
    cur.execute("select 1")

    assert cur.fetchone() == (None, "", "plain", None)


def test_dbapi_embedded_prepared_params(monkeypatch):
    fake_statement = FakeStatement([(1, "a")])

    def fake_cls(name):
        assert name == "%SQL.Statement"
        return FakeStatementFactory(fake_statement)

    monkeypatch.setattr(_iris_ep, "cls", fake_cls, raising=False)
    monkeypatch.setattr(
        _iris_ep.dbapi._runtime_manager,
        "get",
        lambda: types.SimpleNamespace(
            embedded_available=True,
            state="embedded-kernel",
            dbapi=None,
        ),
    )

    conn = iris.dbapi.connect(mode="embedded")
    cur = conn.cursor()

    cur.execute("select * from Demo where id=? and name=?", (7, "z"))

    assert fake_statement.prepare_seen == "select * from Demo where id=? and name=?"
    assert fake_statement.execute_args == (7, "z")
    assert fake_statement.execute_kwargs == {}


def test_dbapi_embedded_prepared_params_normalize_empty_string(monkeypatch):
    fake_statement = FakeStatement([(1, "a")])

    def fake_cls(name):
        assert name == "%SQL.Statement"
        return FakeStatementFactory(fake_statement)

    monkeypatch.setattr(_iris_ep, "cls", fake_cls, raising=False)
    monkeypatch.setattr(
        _iris_ep.dbapi._runtime_manager,
        "get",
        lambda: types.SimpleNamespace(
            embedded_available=True,
            state="embedded-kernel",
            dbapi=None,
        ),
    )

    conn = iris.dbapi.connect(mode="embedded")
    cur = conn.cursor()

    cur.execute("select * from Demo where a=? and b=? and c=?", ("", None, "z"))

    assert fake_statement.execute_args == ("\x00", "", "z")


def test_dbapi_embedded_prepared_params_normalize_decimal(monkeypatch):
    fake_statement = FakeStatement([(1, "a")])

    def fake_cls(name):
        assert name == "%SQL.Statement"
        return FakeStatementFactory(fake_statement)

    monkeypatch.setattr(_iris_ep, "cls", fake_cls, raising=False)
    monkeypatch.setattr(
        _iris_ep.dbapi._runtime_manager,
        "get",
        lambda: types.SimpleNamespace(
            embedded_available=True,
            state="embedded-kernel",
            dbapi=None,
        ),
    )

    conn = iris.dbapi.connect(mode="embedded")
    cur = conn.cursor()

    cur.execute("select * from Demo where amount=?", (Decimal("123.45"),))

    assert fake_statement.execute_args == ("123.45",)


def test_dbapi_embedded_prepared_dict_params_normalize_empty_string(monkeypatch):
    fake_statement = FakeStatement([(1, "a")])

    def fake_cls(name):
        assert name == "%SQL.Statement"
        return FakeStatementFactory(fake_statement)

    monkeypatch.setattr(_iris_ep, "cls", fake_cls, raising=False)
    monkeypatch.setattr(
        _iris_ep.dbapi._runtime_manager,
        "get",
        lambda: types.SimpleNamespace(
            embedded_available=True,
            state="embedded-kernel",
            dbapi=None,
        ),
    )

    conn = iris.dbapi.connect(mode="embedded")
    cur = conn.cursor()

    cur.execute("select * from Demo where a=:a and b=:b", {"a": "", "b": None})

    assert fake_statement.prepare_seen == "select * from Demo where a=? and b=?"
    assert fake_statement.execute_args == ("\x00", "")
    assert fake_statement.execute_kwargs == {}


def test_dbapi_embedded_prepared_dict_params_normalize_decimal(monkeypatch):
    fake_statement = FakeStatement([(1, "a")])

    def fake_cls(name):
        assert name == "%SQL.Statement"
        return FakeStatementFactory(fake_statement)

    monkeypatch.setattr(_iris_ep, "cls", fake_cls, raising=False)
    monkeypatch.setattr(
        _iris_ep.dbapi._runtime_manager,
        "get",
        lambda: types.SimpleNamespace(
            embedded_available=True,
            state="embedded-kernel",
            dbapi=None,
        ),
    )

    conn = iris.dbapi.connect(mode="embedded")
    cur = conn.cursor()

    cur.execute("select * from Demo where amount=:amount", {"amount": Decimal("9.50")})

    assert fake_statement.prepare_seen == "select * from Demo where amount=?"
    assert fake_statement.execute_args == ("9.50",)
    assert fake_statement.execute_kwargs == {}


def test_dbapi_embedded_prepared_dict_params_rewrite_repeated_names(monkeypatch):
    fake_statement = FakeStatement([(1, "a")])

    def fake_cls(name):
        assert name == "%SQL.Statement"
        return FakeStatementFactory(fake_statement)

    monkeypatch.setattr(_iris_ep, "cls", fake_cls, raising=False)
    monkeypatch.setattr(
        _iris_ep.dbapi._runtime_manager,
        "get",
        lambda: types.SimpleNamespace(
            embedded_available=True,
            state="embedded-kernel",
            dbapi=None,
        ),
    )

    conn = iris.dbapi.connect(mode="embedded")
    cur = conn.cursor()

    cur.execute(
        "select ':ignored' as literal, :x + :y as total, :x as again",
        {"x": 2, "y": 3},
    )

    assert fake_statement.prepare_seen == (
        "select ':ignored' as literal, ? + ? as total, ? as again"
    )
    assert fake_statement.execute_args == (2, 3, 2)
    assert fake_statement.execute_kwargs == {}


def test_dbapi_embedded_prepared_dict_params_missing_name(monkeypatch):
    fake_statement = FakeStatement([(1, "a")])

    def fake_cls(name):
        assert name == "%SQL.Statement"
        return FakeStatementFactory(fake_statement)

    monkeypatch.setattr(_iris_ep, "cls", fake_cls, raising=False)
    monkeypatch.setattr(
        _iris_ep.dbapi._runtime_manager,
        "get",
        lambda: types.SimpleNamespace(
            embedded_available=True,
            state="embedded-kernel",
            dbapi=None,
        ),
    )

    conn = iris.dbapi.connect(mode="embedded")
    cur = conn.cursor()

    with pytest.raises(iris.dbapi.InterfaceError, match="Missing named SQL parameter"):
        cur.execute("select :missing", {"other": 1})


def test_dbapi_embedded_insert_sets_rowcount(monkeypatch):
    fake_statement = FakeStatementWithRowcount([1])

    def fake_cls(name):
        assert name == "%SQL.Statement"
        return FakeStatementFactory(fake_statement)

    monkeypatch.setattr(_iris_ep, "cls", fake_cls, raising=False)
    monkeypatch.setattr(
        _iris_ep.dbapi._runtime_manager,
        "get",
        lambda: types.SimpleNamespace(
            embedded_available=True,
            state="embedded-kernel",
            dbapi=None,
        ),
    )

    conn = iris.dbapi.connect(mode="embedded")
    cur = conn.cursor()

    cur.execute("insert into Demo (name) values (?)", ("x",))

    assert cur.description is None
    assert cur.rowcount == 1


def test_dbapi_embedded_executemany_sums_rowcount(monkeypatch):
    fake_statement = FakeStatementWithRowcount([1, 1, 1])

    def fake_cls(name):
        assert name == "%SQL.Statement"
        return FakeStatementFactory(fake_statement)

    monkeypatch.setattr(_iris_ep, "cls", fake_cls, raising=False)
    monkeypatch.setattr(
        _iris_ep.dbapi._runtime_manager,
        "get",
        lambda: types.SimpleNamespace(
            embedded_available=True,
            state="embedded-kernel",
            dbapi=None,
        ),
    )

    conn = iris.dbapi.connect(mode="embedded")
    cur = conn.cursor()

    cur.executemany("insert into Demo (name) values (?)", [("a",), ("b",), ("c",)])

    assert cur.description is None
    assert cur.rowcount == 3


def test_dbapi_embedded_fetches_stream_values(monkeypatch):
    character_stream = FakeIRISStream("%Stream.GlobalCharacter", "long text")
    binary_stream = FakeIRISStream("%Stream.GlobalBinary", "\x00\xff")
    fake_statement = FakeStatement([(character_stream, binary_stream)])

    def fake_cls(name):
        assert name == "%SQL.Statement"
        return FakeStatementFactory(fake_statement)

    monkeypatch.setattr(_iris_ep, "cls", fake_cls, raising=False)
    monkeypatch.setattr(
        _iris_ep.dbapi._runtime_manager,
        "get",
        lambda: types.SimpleNamespace(
            embedded_available=True,
            state="embedded-kernel",
            dbapi=None,
        ),
    )

    conn = iris.dbapi.connect(mode="embedded")
    cur = conn.cursor()

    cur.execute("select long_text, long_bin from Demo")

    assert cur.fetchone() == ("long text", b"\x00\xff")
    assert character_stream.rewound
    assert binary_stream.rewound


def test_dbapi_embedded_fetches_packed_stream_reference_strings(monkeypatch):
    character_ref = public_iris.IRISList([
        "1",
        "%Stream.GlobalCharacter",
        "^FAKE.STREAM",
    ]).to_param().decode("latin-1")
    binary_ref = public_iris.IRISList([
        "2",
        "%Stream.GlobalBinary",
        "^FAKE.STREAM",
    ]).to_param().decode("latin-1")
    fake_global = FakeStreamGlobal(
        {
            ("1",): "2,10",
            ("1", "1"): "long ",
            ("1", "2"): "text",
            ("2",): "2,5",
            ("2", "1"): "\x00",
            ("2", "2"): "\xffabc",
        }
    )

    monkeypatch.setattr(public_iris, "gref", lambda root: fake_global)

    assert embedded_dbapi._normalize_embedded_result_value(character_ref) == "long text"
    assert embedded_dbapi._normalize_embedded_result_value(binary_ref) == b"\x00\xffabc"


def test_dbapi_embedded_fetches_vector_values_with_getrow(monkeypatch):
    fake_statement = FakeVectorStatement(
        [(1, "row one", "1,2,3")],
        [
            FakeMetadataColumn("id", client_type=5),
            FakeMetadataColumn("name", client_type=10, runtime_type="%Library.String"),
            FakeMetadataColumn(
                "embedding",
                client_type=10,
                runtime_type="%Library.Vector",
                sql_category="VECTOR",
            ),
        ],
    )

    def fake_cls(name):
        assert name == "%SQL.Statement"
        return FakeStatementFactory(fake_statement)

    monkeypatch.setattr(_iris_ep, "cls", fake_cls, raising=False)
    monkeypatch.setattr(
        _iris_ep.dbapi._runtime_manager,
        "get",
        lambda: types.SimpleNamespace(
            embedded_available=True,
            state="embedded-kernel",
            dbapi=None,
        ),
    )

    conn = iris.dbapi.connect(mode="embedded")
    cur = conn.cursor()

    cur.execute("select id, name, embedding from Demo")

    assert cur.fetchone() == (1, "row one", "1,2,3")


def test_dbapi_embedded_fetches_list_values_from_metadata(monkeypatch):
    payload = public_iris.IRISList([1, "two", Decimal("3.5")])
    raw_payload = payload.to_param().decode("latin-1")
    fake_statement = FakeVectorStatement(
        [(1, raw_payload)],
        [
            FakeMetadataColumn("id", client_type=5),
            FakeMetadataColumn(
                "payload",
                client_type=10,
                runtime_type="%Library.List",
                sql_category="LIST",
            ),
        ],
    )

    def fake_cls(name):
        assert name == "%SQL.Statement"
        return FakeStatementFactory(fake_statement)

    monkeypatch.setattr(_iris_ep, "cls", fake_cls, raising=False)
    monkeypatch.setattr(
        _iris_ep.dbapi._runtime_manager,
        "get",
        lambda: types.SimpleNamespace(
            embedded_available=True,
            state="embedded-kernel",
            dbapi=None,
        ),
    )

    conn = iris.dbapi.connect(mode="embedded")
    cur = conn.cursor()

    cur.execute("select id, payload from Demo")
    row = cur.fetchone()

    assert row[0] == 1
    assert isinstance(row[1], public_iris.IRISList)
    assert list(row[1]) == [1, "two", Decimal("3.5")]


def test_dbapi_embedded_prefers_sql_statement(monkeypatch):
    fake_statement = FakeStatement([(3, "c"), (4, "d")])

    def fake_cls(name):
        assert name == "%SQL.Statement"
        return FakeStatementFactory(fake_statement)

    monkeypatch.setattr(_iris_ep, "cls", fake_cls, raising=False)
    monkeypatch.setattr(
        _iris_ep.dbapi._runtime_manager,
        "get",
        lambda: types.SimpleNamespace(
            embedded_available=True,
            state="embedded-kernel",
            dbapi=None,
        ),
    )

    conn = iris.dbapi.connect(mode="embedded")
    cur = conn.cursor()
    cur.execute("select * from Demo where id=?", (3,))

    # %SQL.Statement path should be used first.
    assert fake_statement.prepare_seen == "select * from Demo where id=?"
    assert fake_statement.execute_args == (3,)
    assert fake_statement.execute_kwargs == {}
    assert cur.fetchall() == [(3, "c"), (4, "d")]


def test_dbapi_embedded_result_without_column_count(monkeypatch):
    fake_statement = FakeStatementNoColumnCount([(42,)])

    def fake_cls(name):
        assert name == "%SQL.Statement"
        return FakeStatementFactory(fake_statement)

    monkeypatch.setattr(_iris_ep, "cls", fake_cls, raising=False)
    monkeypatch.setattr(
        _iris_ep.dbapi._runtime_manager,
        "get",
        lambda: types.SimpleNamespace(
            mode="auto",
            embedded_available=True,
            state="embedded-local",
            dbapi=None,
        ),
    )

    conn = iris.dbapi.connect()
    cur = conn.cursor()
    cur.execute("select 1")

    assert cur.fetchone() == (42,)


def test_dbapi_embedded_result_without_column_count_does_not_hang(monkeypatch):
    fake_statement = FakeStatementNoColumnCountInfinite([])

    def fake_cls(name):
        assert name == "%SQL.Statement"
        return FakeStatementFactory(fake_statement)

    monkeypatch.setattr(_iris_ep, "cls", fake_cls, raising=False)
    monkeypatch.setattr(
        _iris_ep.dbapi._runtime_manager,
        "get",
        lambda: types.SimpleNamespace(
            mode="auto",
            embedded_available=True,
            state="embedded-local",
            dbapi=None,
        ),
    )

    conn = iris.dbapi.connect()
    cur = conn.cursor()
    cur.execute("select 1")

    assert cur.fetchone() == (1,)


def test_dbapi_embedded_falls_back_to_getdata_accessor(monkeypatch):
    fake_statement = FakeStatementGetDataOnly([(7, "gd")])

    def fake_cls(name):
        assert name == "%SQL.Statement"
        return FakeStatementFactory(fake_statement)

    monkeypatch.setattr(_iris_ep, "cls", fake_cls, raising=False)
    monkeypatch.setattr(
        _iris_ep.dbapi._runtime_manager,
        "get",
        lambda: types.SimpleNamespace(
            mode="auto",
            embedded_available=True,
            state="embedded-local",
            dbapi=None,
        ),
    )

    conn = iris.dbapi.connect()
    cur = conn.cursor()
    cur.execute("select 1")

    assert cur.fetchone() == (7, "gd")


def test_dbapi_embedded_falls_back_to_projection_attributes(monkeypatch):
    fake_statement = FakeStatementAttrOnly([(9,)], ["result"])

    def fake_cls(name):
        assert name == "%SQL.Statement"
        return FakeStatementFactory(fake_statement)

    monkeypatch.setattr(_iris_ep, "cls", fake_cls, raising=False)
    monkeypatch.setattr(
        _iris_ep.dbapi._runtime_manager,
        "get",
        lambda: types.SimpleNamespace(
            mode="auto",
            embedded_available=True,
            state="embedded-local",
            dbapi=None,
        ),
    )

    conn = iris.dbapi.connect()
    cur = conn.cursor()
    cur.execute("SELECT 1 AS result")

    assert cur.fetchone() == (9,)


def test_dbapi_embedded_mode_accepts_embedded_local(monkeypatch):
    fake_statement = FakeStatement([(11, "local")])

    def fake_cls(name):
        assert name == "%SQL.Statement"
        return FakeStatementFactory(fake_statement)

    monkeypatch.setattr(_iris_ep, "cls", fake_cls, raising=False)
    monkeypatch.setattr(
        _iris_ep.dbapi._runtime_manager,
        "get",
        lambda: types.SimpleNamespace(
            embedded_available=True,
            state="embedded-local",
            dbapi=None,
        ),
    )

    conn = iris.dbapi.connect(mode="embedded")
    cur = conn.cursor()
    cur.execute("select 1")

    assert fake_statement.prepare_seen == "select 1"
    assert cur.fetchone() == (11, "local")
