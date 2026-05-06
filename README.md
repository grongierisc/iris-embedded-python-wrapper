# iris-embedded-python-wrapper

`iris-embedded-python-wrapper` provides a stable `import iris` facade for
InterSystems IRIS Python projects.

It lets the same application code work across the common IRIS Python runtimes:

- IRIS embedded Python launched by IRIS, for example `iris python iris`
  or `iris session iris` followed by `:py`
- regular `python3` using an installed IRIS embedded Python runtime
- remote/native connections through the official `intersystems-irispython`
  SDK

The wrapper keeps `iris.cls(...)`, `iris.connect(...)`, and `iris.dbapi`
available from one package while making the active runtime explicit through
`iris.runtime`.

More details about embedded Python in IRIS are available in the
[IRIS documentation](https://docs.intersystems.com/irislatest/csp/docbook/DocBook.UI.Page.cls?KEY=AFL_epython).

## What this project brings

Without this wrapper, Python code often has to care about where it is running:

- the embedded `iris` module is available inside an IRIS Python kernel, but not
  automatically from a normal `python3` process
- the official remote SDK also exposes an `iris` package, so local embedded,
  embedded-kernel, and remote/native imports can shadow each other
- `iris.cls(...)` and DB-API connection behavior differ between embedded and
  remote execution
- Unix dynamic library setup must happen before Python starts, while Windows
  needs DLL directory registration
- embedded `%SQL.Statement` and remote DB-API can disagree on IRIS boundary
  values such as SQL `NULL` and empty string

This package gives you:

- a unified `iris.runtime` state model (`auto`, `embedded`, `native`)
- `iris.connect(path=<iris_install_dir>)` to enable an embedded-local runtime
  without `IRISINSTALLDIR`
- an `iris.dbapi` facade that can use embedded SQL or the official native
  DB-API driver
- `iris.dbapi.connect(path=<iris_install_dir>)` to configure embedded-local
  mode and return a DB-API connection in one call
- native object proxy support through `iris.cls(...)` when a remote IRIS handle
  is bound
- consistent embedded DB-API normalization for SQL `NULL` and empty strings
- automatic Windows `os.add_dll_directory(...)` handling for IRIS libraries
- Docker and GitHub test flows that run against the official IRIS community
  image without writing into the mounted source tree

## Runtime modes

| Runtime | How it is used | Main entry points |
| --- | --- | --- |
| `embedded-kernel` | Python is started by IRIS | `iris python iris`, `iris session iris` then `:py` |
| `embedded-local` | normal `python3` loads IRIS embedded libraries | `IRISINSTALLDIR`, loader path, `iris.connect(path=...)`, or `iris.dbapi.connect(path=...)` |
| `native-remote` | Python connects to a running IRIS instance | `iris.connect(...)`, `iris.runtime.configure(...)`, `iris.dbapi.connect(mode="native")` |
| `unavailable` | no embedded runtime or native binding is available | configure a runtime before using IRIS APIs |

## Newer features

- `iris.connect(path=...)` can configure the embedded runtime on demand when
  the IRIS install directory is known but `IRISINSTALLDIR` is not set.
- `iris.dbapi.connect(path=...)` uses the same embedded runtime configuration
  path and returns an embedded DB-API connection.
- Explicit `path=...` loading validates that `pythonint` came from that IRIS
  installation and reports Unix loader-path failures with the required
  `LD_LIBRARY_PATH` or `DYLD_LIBRARY_PATH` setup.
- `iris.runtime` is the single source of truth for runtime state and backend
  bindings.
- `iris.dbapi.connect(mode="auto")` chooses embedded or native DB-API based on
  explicit arguments and runtime state.
- Native driver loading prefers the official `intersystems-irispython` SDK and
  only falls back to the community compatibility module when the official SDK
  is unavailable.
- Unit tests isolate filesystem/CPF behavior from real `iris merge`; real IRIS
  kernel and `:py` checks live in e2e tests.

## Prerequisites

To use embedded-local or embedded-kernel mode, you need an InterSystems IRIS
installation (more details can be found
[here](https://docs.intersystems.com/irislatest/csp/docbook/DocBook.UI.Page.cls?KEY=PAGE_deployment_install)).

For remote/native mode, you need a running IRIS instance reachable by the
official native driver.

For embedded access from outside an IRIS kernel, configure
[Service Call-In](#configuration-of-service-call-in) and
[environment variables](#environment-variables).

### Configuration of Service Call-In

In the Management Portal, go to System Administration > Security > Services, select %Service_CallIn, and check the Service Enabled box.

More details can be found in the [IRIS documentation](https://docs.intersystems.com/irislatest/csp/docbook/DocBook.UI.Page.cls?KEY=GEPYTHON_prereqs)

### Environment Variables

Use the following environment variables as needed:

- `IRISINSTALLDIR`: path to the IRIS installation directory
- `LD_LIBRARY_PATH`: Linux loader path for IRIS shared libraries
- `DYLD_LIBRARY_PATH`: macOS loader path for IRIS shared libraries, where
  allowed by the Python launcher
- `IRISUSERNAME`: username for remote/native test connections
- `IRISPASSWORD`: password for remote/native test connections
- `IRISNAMESPACE`: namespace for remote/native test connections

`IRISINSTALLDIR` is enough for many wrapper-level checks, but embedded-local
execution from regular `python3` on Unix also needs the loader path configured
before Python starts. `iris.connect(path=...)` can configure Python import paths
at runtime, but it cannot repair Unix dynamic loader resolution after the
process has already started. If `pythonint` is found but its dependent shared
libraries are not, the runtime error names the loader-path variable that must
include the IRIS `bin` directory.

#### Linux and macOS

For Linux and macOS, set the environment variables as follows:

```bash
export IRISINSTALLDIR=/opt/iris
export LD_LIBRARY_PATH=$IRISINSTALLDIR/bin:$LD_LIBRARY_PATH
# for macOS
export DYLD_LIBRARY_PATH=$IRISINSTALLDIR/bin:$DYLD_LIBRARY_PATH
# for remote/native connection tests
export IRISUSERNAME=SuperUser
export IRISPASSWORD=<password>
export IRISNAMESPACE=USER
```

#### Windows

For Windows, set the IRIS install directory as follows:
    
```bash
set IRISINSTALLDIR=C:\path\to\iris
```

For Python 3.8 and newer, the wrapper automatically registers the IRIS `bin`
directory with `os.add_dll_directory()` when `IRISINSTALLDIR` is set. Update
`PATH` only when using older Python versions or external tools that need IRIS
DLLs:

```bash
set PATH=%IRISINSTALLDIR%\bin;%PATH%
```

Set the IRIS username, password, and namespace when using remote/native
connections:

```bash
set IRISUSERNAME=SuperUser
set IRISPASSWORD=<password>
set IRISNAMESPACE=USER
```

#### PowerShell

For PowerShell, you can set the environment variables as follows:

```powershell
$env:IRISINSTALLDIR="C:\path\to\iris"
$env:IRISUSERNAME="SuperUser"
$env:IRISPASSWORD="<password>"
$env:IRISNAMESPACE="USER"
```

### Installation

```bash
pip install iris-embedded-python-wrapper
```

## Usage

Use this package when you want one Python import path across embedded and
remote IRIS code:

1. `import iris` and call IRIS classes with `iris.cls(...)`
2. inspect or force the active runtime with `iris.runtime`
3. enable embedded-local mode with `iris.connect(path=...)` or
   `iris.dbapi.connect(path=...)`
4. connect to remote IRIS through the official native driver
5. use `iris.dbapi` for embedded or native SQL access
6. bind or unbind a virtual environment to IRIS embedded Python with
   `bind_iris` and `unbind_iris`

### Basic embedded usage

Inside an IRIS embedded Python kernel, `import iris` exposes the embedded IRIS
APIs:

```python
import iris
iris.system.Version.GetVersion()
```

Output:

```python
'IRIS for UNIX (Apple Mac OS X for x86-64) 2024.3 (Build 217U) Thu Nov 14 2024 17:29:23 EST'
```

If the wrapper is imported where no embedded runtime or native connection is
available, IRIS APIs are not silently usable. Configure embedded mode with
`IRISINSTALLDIR` or `iris.connect(path=...)`, or configure native mode with a
remote connection.

### Unified runtime context

The wrapper now uses a unified runtime API through `iris.runtime`.

#### Embedded runtime

The wrapper can run in two embedded contexts:

- `embedded-kernel`: Python is launched by IRIS, for example with
  `iris python iris` or `iris session iris` followed by `:py`
- `embedded-local`: regular `python3` loads the IRIS embedded Python libraries
  from an installed IRIS instance

In `embedded-kernel`, IRIS has already loaded the runtime. Set `PYTHONPATH` to
the project or installed package location when you need the wrapper instead of
the built-in `iris` module:

```bash
PYTHONPATH=/path/to/iris-embedded-python-wrapper iris python iris
```

For an interactive session:

```bash
PYTHONPATH=/path/to/iris-embedded-python-wrapper iris session iris
USER>:py
>>> import iris
>>> iris.runtime.get().state
'embedded-kernel'
```

In `embedded-local`, configure the IRIS install directory and loader path before
starting Python, or provide the install directory at runtime with
`iris.connect(path=...)` as described below.

#### Runtime model

- `iris.runtime.mode`: selected policy (`auto`, `embedded`, `native`)
- `iris.runtime.state`: detected runtime (`embedded-kernel`, `embedded-local`, `native-remote`, `unavailable`)
- `iris.runtime.embedded_available`: whether embedded backend can be used
- `iris.runtime.iris`: currently bound native object API handle (optional)
- `iris.runtime.dbapi`: optional explicitly bound DB-API connection

#### Runtime control API

- `iris.runtime.get()`
- `iris.runtime.configure(mode="auto", install_dir=None, iris=None, dbapi=None, native_connection=None)`
- `iris.runtime.reset()`

`mode` is optional in `runtime.configure(...)`.

- If `iris`, `native_connection`, or `dbapi` is provided, runtime infers native mode.
- If no connection handle is provided, runtime stays in auto/embedded detection flow.

`runtime.configure(...)` also accepts an `IRISConnection` and auto-converts it to an IRIS handle via `createIRIS(...)` for `iris.cls(...)` routing.

#### Remote `iris.cls(...)`: before and after

The official native API is explicit and low-level. Without the wrapper, remote
code normally keeps an IRIS handle and calls helper methods for every class
method, object method, property read, and property write:

```python
import iris

conn = iris.connect("localhost", 1972, "USER", "SuperUser", "<password>")
db = iris.createIRIS(conn)

req = db.classMethodValue("Ens.StringRequest", "%New")
db.set(req, "StringValue", "hello")
value = db.get(req, "StringValue")
db.invoke(req, "SomeInstanceMethod")

result = db.classMethodValue("MyApp.Service", "SomeClassMethod", value)
# Some SDK versions also expose invokeClassMethod(...).
same_result = db.invokeClassMethod("MyApp.Service", "SomeClassMethod", value)
```

With this wrapper, bind the native connection once and use the same
`iris.cls(...)` shape you would use in embedded Python. The proxy maps a leading
underscore to `%`, so `_New()` calls `%New`.

```python
import iris

conn = iris.connect("localhost", 1972, "USER", "SuperUser", "<password>")
iris.runtime.configure(native_connection=conn)

req = iris.cls("Ens.StringRequest")._New()
req.StringValue = "hello"
value = req.StringValue
req.SomeInstanceMethod()

result = iris.cls("MyApp.Service").SomeClassMethod(value)
```

This keeps remote/native code close to embedded code and removes most direct
use of `classMethodValue(...)`, `invokeClassMethod(...)`, `invoke(...)`,
`get(...)`, and `set(...)` from application code.

#### Examples

Force native object API routing:

```python
import iris

conn = iris.connect("localhost", 1972, "USER", "SuperUser", "<password>")
iris.runtime.configure(mode="native", native_connection=conn)

obj = iris.cls("Ens.StringRequest")._New()
```

Native routing with inferred mode and auto-conversion from `IRISConnection`:

```python
import iris

conn = iris.connect("localhost", 1972, "USER", "SuperUser", "<password>")
iris.runtime.configure(native_connection=conn)

obj = iris.cls("Ens.StringRequest")._New()
```

Force embedded routing:

```python
import iris

iris.runtime.configure(mode="embedded")
obj = iris.cls("Ens.StringRequest")._New()
```

Enable embedded routing with an explicit IRIS installation directory:

```python
import iris

iris.connect(path="/opt/iris")
obj = iris.cls("Ens.StringRequest")._New()
```

This is useful when `IRISINSTALLDIR` is not set. On Linux and macOS, the
native library path still needs to be configured before Python starts as shown
in the environment setup section; `path=...` configures the wrapper, but it
cannot change Unix dynamic loader resolution for already-started processes.
The path must point to an IRIS installation directory with `bin` and
`lib/python` subdirectories; invalid paths fail before the wrapper mutates
Python import paths or loader paths. For explicit `path=...`, the wrapper also
removes stale `pythonint` modules for the import attempt and verifies that the
loaded `pythonint.__file__` is under that installation's `bin` or `lib/python`
directory.

`iris.connect(path=...)` returns the runtime context. If the loaded embedded
backend does not expose a callable `connect`, the wrapper emits a
`RuntimeWarning`; use `iris.dbapi.connect(path=...)` when you want a DB-API
connection in one call.

Reset to automatic detection:

```python
import iris

iris.runtime.reset()
```

### DB-API (`iris.dbapi`)

The wrapper exposes a DB-API facade at `iris.dbapi`.

#### Supported subset

- `iris.dbapi.connect(...)`
- Connection: `cursor()`, `close()`, `commit()`, `rollback()`
- Cursor: `execute()`, `fetchone()`, `fetchmany()`, `fetchall()`, iteration, `close()`
- PEP 249 metadata: `apilevel`, `threadsafety`, `paramstyle`
- PEP 249 exceptions: `Error`, `InterfaceError`, `OperationalError`, and related subclasses

#### Value normalization

For the embedded `%SQL.Statement` backend, the wrapper normalizes IRIS SQL/ObjectScript string boundary values to Python values so embedded and remote DB-API behave the same way:

- SQL `NULL` is returned as Python `None`
- SQL empty string is returned as Python `""`
- Python `None` passed as a parameter remains SQL `NULL`
- Python `""` passed as a parameter is written as an SQL empty string, not SQL `NULL`

This normalization is limited to the embedded DB-API path. Native/remote DB-API values are returned by the official driver.

For the native object proxy path (`iris.cls(...)` with `iris.runtime` configured for native mode), the wrapper also normalizes declared scalar string properties:

- `%String` / `%RawString` scalar properties that come back as `None` from the native proxy are returned as Python `""`
- non-string properties are left unchanged
- collection-valued properties are left unchanged
- arbitrary method return values are left unchanged

#### Connect modes

`iris.dbapi.connect()` accepts `mode="auto" | "embedded" | "native"`.

- `mode="embedded"`: forces embedded SQL backend via `%SQL.Statement`
- `mode="native"`: forces native DB-API backend via the official module `iris.dbapi`
- `mode="auto"`:
	- if explicit remote arguments are provided (`hostname`, `port`, `namespace`, etc.), uses native
	- if `iris.runtime.dbapi` is already bound, reuses that DB-API connection
	- otherwise uses embedded (`%SQL.Statement`) only when runtime policy is not native
	- if `iris.runtime` is configured for native mode without a bound DB-API connection, raises an error instead of silently falling back to embedded
	- raises an error if embedded runtime is not available

Native resolution uses the official module path `iris.dbapi` (not `intersystems_iris.dbapi`).

`mode` is optional for DB-API.

- With explicit remote arguments (`hostname`, `port`, `namespace`, `username`, `password`, etc.), DB-API infers native.
- With `path=...`, DB-API configures embedded-local runtime and returns an
  embedded DB-API connection. `mode` must be `auto` or `embedded`.
- With `iris.runtime.configure(dbapi=conn)`, DB-API auto mode reuses the bound native connection.
- Without remote arguments or a bound runtime DB-API connection, DB-API auto mode uses embedded unless `iris.runtime` is explicitly in native mode.

`iris.connect(path=...)` and `iris.dbapi.connect(path=...)` share the same
embedded runtime configuration behavior, but return different things:

- `iris.connect(path=...)` returns the `RuntimeContext`
- `iris.dbapi.connect(path=...)` returns a DB-API connection

`iris.dbapi.connect(path=...)` accepts embedded DB-API options such as
`namespace=...` and `isolation_level=...`. It rejects native mode and native
connection arguments such as `hostname`, `port`, `username`, and `password`.
The path is validated with the same rules as `iris.connect(path=...)`.

#### Examples

Embedded mode:

```python
import iris

conn = iris.dbapi.connect()
cur = conn.cursor()
cur.execute("SELECT Name FROM Sample.Person")
rows = cur.fetchall()
cur.close()
conn.close()
```

Embedded-local mode with an explicit IRIS installation directory:

```python
import iris

conn = iris.dbapi.connect(path="/opt/iris", namespace="USER")
cur = conn.cursor()
cur.execute("SELECT 1")
print(cur.fetchone())
```

Native mode:

```python
import iris

conn = iris.dbapi.connect(
		mode="native",
		hostname="localhost",
		port=1972,
		namespace="USER",
		username="SuperUser",
		password="<password>",
)
cur = conn.cursor()
cur.execute("SELECT 1")
print(cur.fetchone())
```

Auto mode with explicit remote arguments (routes to native):

```python
import iris

conn = iris.dbapi.connect(
		hostname="localhost",
		port=1972,
		namespace="USER",
		username="SuperUser",
		password="<password>",
)
```

Auto mode with a runtime-bound native DB-API connection:

```python
import iris

conn = iris.dbapi.connect(
		mode="native",
		hostname="localhost",
		port=1972,
		namespace="USER",
		username="SuperUser",
		password="<password>",
)
iris.runtime.configure(dbapi=conn)

same_conn = iris.dbapi.connect(mode="auto")
assert same_conn is conn
```

#### Runtime independence

`iris.dbapi.connect()` is independent from `iris.runtime` by default.

Calling `iris.dbapi.connect(...)` does not auto-bind a connection into `iris.runtime.dbapi`.
If you need runtime-managed DB-API binding, bind it explicitly with `iris.runtime.configure(dbapi=conn)`.
Once bound, `iris.dbapi.connect(mode="auto")` reuses that connection instead of creating a new one.

### Bind a virtual environment to embedded Python in IRIS

You can bind a Python virtual environment into the IRIS embedded Python
configuration:

```bash
bind_iris
```

Output:

```bash
(.venv) demo ‹master*›$ bind_iris
INFO:iris_utils._find_libpython:Created backup at /opt/intersystems/iris/iris.cpf.fa76423a7b924eb085911690c8266129
INFO:iris_utils._find_libpython:Created merge file at /opt/intersystems/iris/iris.cpf.python_merge
up  IRIS              2024.3.0.217.0    1972   /opt/intersystems/iris

Username: SuperUser
Password: ***
IRIS Merge of /opt/intersystems/iris/iris.cpf.python_merge into /opt/intersystems/iris/iris.cpf
IRIS Merge completed successfully
INFO:iris_utils._find_libpython:PythonRuntimeLibrary path set to /usr/local/Cellar/python@3.11/3.11.10/Frameworks/Python.framework/Versions/3.11/Python
INFO:iris_utils._find_libpython:PythonPath set to /demo/.venv/lib/python3.11/site-packages
INFO:iris_utils._find_libpython:PythonRuntimeLibraryVersion set to 3.11
```

You may need IRIS administrator credentials to bind the virtual environment to
embedded Python in IRIS.

On Windows, restart IRIS after changing the embedded Python configuration.

### Unbind a virtual environment from embedded Python in IRIS

```bash
unbind_iris
```

Output:

```bash
(.venv) demo ‹master*›$ unbind_iris
INFO:iris_utils._find_libpython:Created merge file at /opt/intersystems/iris/iris.cpf.python_merge
up  IRIS              2024.3.0.217.0    1972   /opt/intersystems/iris

Username: SuperUser
Password: ***
IRIS Merge of /opt/intersystems/iris/iris.cpf.python_merge into /opt/intersystems/iris/iris.cpf
IRIS Merge completed successfully
INFO:iris_utils._find_libpython:PythonRuntimeLibrary path set to /usr/local/Cellar/python@3.11/3.11.10/Frameworks/Python.framework/Versions/3.11/Python
INFO:iris_utils._find_libpython:PythonPath set to /Other/.venv/lib/python3.11/site-packages
INFO:iris_utils._find_libpython:PythonRuntimeLibraryVersion set to 3.11
```

## Running tests

### Local `.venv`

For pure unit tests, use the project virtual environment and keep CPF merge
tests on temporary files:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e . pytest
env -u ISC_CPF_MERGE_FILE python -m pytest tests -q
```

Embedded-local e2e tests from `python3` also need an IRIS installation and the
platform loader path configured before Python starts:

```bash
export IRISINSTALLDIR=/opt/iris
export LD_LIBRARY_PATH=$IRISINSTALLDIR/bin:$LD_LIBRARY_PATH
python -m pytest tests/iris/test_dbapi_e2e.py -q
```

On macOS use `DYLD_LIBRARY_PATH` where your shell and Python launcher allow it.
On Windows, the wrapper registers the IRIS `bin` directory with
`os.add_dll_directory()` when `IRISINSTALLDIR` is set.

### Docker

Run the test suite in Docker with the vanilla official InterSystems IRIS
community image:

```bash
./scripts/test-docker.sh
```

Pass any pytest selector or option after the script name:

```bash
./scripts/test-docker.sh tests/iris/test_dbapi_embedded.py -q
```

`scripts/test-docker.sh` starts `docker-compose-test-preview.yml`, waits for
IRIS, unlocks the default test passwords, and then delegates pytest execution to
`scripts/run-pytest-in-iris.sh`. The in-container runner is the single source of
truth for GitHub Actions and local Docker runs.

The container test flow is source-based:

- the repository is mounted at `/irisdev/app` read-only
- `PYTHONPATH=/irisdev/app` exposes the working tree
- the test virtual environment is created under `/tmp`
- pytest bytecode/cache writes are disabled
- `ISC_CPF_MERGE_FILE` is unset before pytest so tests cannot rewrite the repo
  merge file

By default `IRIS_E2E_MODES=embedded,remote`, so remote DB-API e2e tests run and
the embedded runtime plus embedded DB-API SQL are required from `python3`.

To test another IRIS image tag:

```bash
IRIS_IMAGE_TAG=latest-preview ./scripts/test-docker.sh
```

## Troubleshooting

You may encounter the following error, here is how to fix them.

### No module named 'pythonint'

This usually means the wrapper cannot find the IRIS embedded Python extension.
Check that `IRISINSTALLDIR` or `path=...` points to the IRIS installation
directory, not a parent directory, and that it contains both `bin` and
`lib/python`.

If the error mentions IRIS shared libraries, configure the platform loader path
before Python starts:

```bash
export IRISINSTALLDIR=/opt/iris
export LD_LIBRARY_PATH=$IRISINSTALLDIR/bin:$LD_LIBRARY_PATH
# macOS
export DYLD_LIBRARY_PATH=$IRISINSTALLDIR/bin:$DYLD_LIBRARY_PATH
```

### IRIS_ACCESSDENIED (-15)

This can occur when Service Call-In is not enabled. Make sure
`%Service_CallIn` is enabled.

### IRIS_ATTACH (-21)

This can occur when the user is not the same as the iris owner. Make sure that the user is the same as the iris owner.

### irisbuiltins.SQLError: <UNIMPLEMENTED>ddtab+82^%qaqpsq

This error can occur when IRIS dependent libraries are not visible to the
dynamic loader. Prefer setting `LD_LIBRARY_PATH` on Linux or `DYLD_LIBRARY_PATH`
on macOS before Python starts, instead of copying IRIS libraries into the
Python installation:

```bash
export IRISINSTALLDIR=/opt/iris
export LD_LIBRARY_PATH=$IRISINSTALLDIR/bin:$LD_LIBRARY_PATH
# macOS
export DYLD_LIBRARY_PATH=$IRISINSTALLDIR/bin:$DYLD_LIBRARY_PATH
```
