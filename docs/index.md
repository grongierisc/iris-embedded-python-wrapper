# iris-embedded-python-wrapper

This is a module that wraps embedded python in the IRIS Dataplateform. It provides a simple interface to run python code in IRIS.

More details can be found in the [IRIS documentation](https://docs.intersystems.com/iris20243/csp/docbook/DocBook.UI.Page.cls?KEY=AFL_epython)

# Pre-requisites

To make use of this module, you need to have the IRIS Dataplatform installed on your machine (more details can be found [here](https://docs.intersystems.com/iris20243/csp/docbook/DocBook.UI.Page.cls?KEY=PAGE_deployment_install)).

Then you must configure the [service callin](#configuration-of-the-service-callin) to allow the python code to be executed and [set the environment variables](#environment-variables).

## Configuration of the service callin

In the Management Portal, go to System Administration > Security > Services, select %Service_CallIn, and check the Service Enabled box.

More details can be found in the [IRIS documentation](https://docs.intersystems.com/iris20243/csp/docbook/DocBook.UI.Page.cls?KEY=GEPYTHON_prereqs)

## Environment Variables

Set the following environment variables :

- IRISINSTALLDIR: The path to the IRIS installation directory
- LD_LIBRARY_PATH: The path to the IRIS library
- IRISUSERNAME: The username to connect to IRIS
- IRISPASSWORD: The password to connect to IRIS
- IRISNAMESPACE: The namespace to connect to IRIS

### For Linux and MacOS

For Linux and MacOS, you can set the environment variables as follows:

```bash
export IRISINSTALLDIR=/opt/iris
export LD_LIBRARY_PATH=$IRISINSTALLDIR/bin:$LD_LIBRARY_PATH
# for MacOS
export DYLD_LIBRARY_PATH=$IRISINSTALLDIR/bin:$DYLD_LIBRARY_PATH
# for IRIS username
export IRISUSERNAME=SuperUser
export IRISPASSWORD=SYS
export IRISNAMESPACE=USER
```

### For windows

For windows, you can set the environment variables as follows:
    
```bash
set IRISINSTALLDIR=C:\path\to\iris
set LD_LIBRARY_PATH=%IRISINSTALLDIR%\bin;%LD_LIBRARY_PATH%
```

Update the library path for windows

```bash
set PATH=%IRISINSTALLDIR%\bin;%PATH%
```

Set the IRIS username, password, and namespace

```bash
set IRISUSERNAME=SuperUser
set IRISPASSWORD=SYS
set IRISNAMESPACE=USER
```

### For PowerShell

For PowerShell, you can set the environment variables as follows:

```powershell
$env:IRISINSTALLDIR="C:\path\to\iris"
$env:PATH="$env:IRISINSTALLDIR\bin;$env:PATH"
$env:IRISUSERNAME="SuperUser"
$env:IRISPASSWORD="SYS"
$env:IRISNAMESPACE="USER"
```

## Installation  

```bash
pip install iris-embedded-python-wrapper
```

# Usage

You can use this module in three ways:

1. Run python code in IRIS
2. Bind a virtual environment to embedded python in IRIS
3. Unbind a virtual environment from embedded python in IRIS

## Run python code in IRIS

Now you can use the module to run python code in IRIS. Here is an example:

```python
import iris
iris.system.Version.GetVersion()
```

Output:

```python
'IRIS for UNIX (Apple Mac OS X for x86-64) 2024.3 (Build 217U) Thu Nov 14 2024 17:29:23 EST'
```

## Unified runtime context

The wrapper now uses a unified runtime API through `iris.runtime`.

### Runtime model

- `iris.runtime.mode`: selected policy (`auto`, `embedded`, `native`)
- `iris.runtime.state`: detected runtime (`embedded-kernel`, `embedded-local`, `native-remote`, `unavailable`)
- `iris.runtime.embedded_available`: whether embedded backend can be used
- `iris.runtime.iris`: currently bound native object API handle (optional)
- `iris.runtime.dbapi`: optional explicitly bound DB-API connection

### Runtime control API

- `iris.runtime.get()`
- `iris.runtime.configure(mode="auto", install_dir=None, iris=None, dbapi=None, native_connection=None)`
- `iris.runtime.reset()`

### Examples

Force native object API routing:

```python
import iris

conn = iris.createConnection("localhost", 1972, "USER", "_SYSTEM", "SYS")
db = iris.createIRIS(conn)
iris.runtime.configure(mode="native", iris=db, native_connection=conn)

obj = iris.cls("Ens.StringRequest")._New()
```

Force embedded routing:

```python
import iris

iris.runtime.configure(mode="embedded")
obj = iris.cls("Ens.StringRequest")._New()
```

Reset to automatic detection:

```python
import iris

iris.runtime.reset()
```

## DB-API (`iris.dbapi`)

The wrapper exposes a DB-API facade at `iris.dbapi`.

### Supported subset

- `iris.dbapi.connect(...)`
- Connection: `cursor()`, `close()`, `commit()`, `rollback()`
- Cursor: `execute()`, `fetchone()`, `fetchmany()`, `fetchall()`, iteration, `close()`
- PEP 249 metadata: `apilevel`, `threadsafety`, `paramstyle`
- PEP 249 exceptions: `Error`, `InterfaceError`, `OperationalError`, and related subclasses

### Connect modes

`iris.dbapi.connect()` accepts `mode="auto" | "embedded" | "native"`.

- `mode="embedded"`: forces embedded SQL backend (`iris.sql`)
- `mode="native"`: forces native DB-API backend via the official module `iris.dbapi`
- `mode="auto"`:
	- if explicit remote arguments are provided (`hostname`, `port`, `namespace`, etc.), uses native
	- otherwise prefers embedded when available
	- falls back to native when embedded is not available

Native resolution uses the official module path `iris.dbapi` (not `intersystems_iris.dbapi`).

### Examples

Embedded mode:

```python
import iris

conn = iris.dbapi.connect(mode="embedded")
cur = conn.cursor()
cur.execute("SELECT Name FROM Sample.Person")
rows = cur.fetchall()
cur.close()
conn.close()
```

Native mode:

```python
import iris

conn = iris.dbapi.connect(
		mode="native",
		hostname="localhost",
		port=1972,
		namespace="USER",
		username="_SYSTEM",
		password="SYS",
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
		username="_SYSTEM",
		password="SYS",
)
```

### Runtime independence

`iris.dbapi.connect()` is independent from `iris.runtime` by default.

Calling `iris.dbapi.connect(...)` does not auto-bind a connection into `iris.runtime.dbapi`.
If you need runtime-managed DB-API binding, bind it explicitly with `iris.runtime.configure(dbapi=conn)`.

## Bind a virtual environment to embedded python in IRIS

You can also bind or unbind an virtual environment to embedded python in IRIS. Here is an example:

```bash
bind_iris
```

Output:

```bash
(.venv) demo ‹master*›$ bind_iris
INFO:iris_utils._find_libpyton:Created backup at /opt/intersystems/iris/iris.cpf.fa76423a7b924eb085911690c8266129
INFO:iris_utils._find_libpyton:Created merge file at /opt/intersystems/iris/iris.cpf.python_merge
up  IRIS              2024.3.0.217.0    1972   /opt/intersystems/iris

Username: SuperUser
Password: ***
IRIS Merge of /opt/intersystems/iris/iris.cpf.python_merge into /opt/intersystems/iris/iris.cpf
IRIS Merge completed successfully
INFO:iris_utils._find_libpyton:PythonRuntimeLibrary path set to /usr/local/Cellar/python@3.11/3.11.10/Frameworks/Python.framework/Versions/3.11/Python
INFO:iris_utils._find_libpyton:PythonPath set to /demo/.venv/lib/python3.11/site-packages
INFO:iris_utils._find_libpyton:PythonRuntimeLibraryVersion set to 3.11
```

You may have to put your admin credentials to bind the virtual environment to the embedded python in IRIS.

In windows, you must restart the IRIS.

## Unbind a virtual environment from embedded python in IRIS

```bash
unbind_iris
```

Output:

```bash
(.venv) demo ‹master*›$ unbind_iris
INFO:iris_utils._find_libpyton:Created merge file at /opt/intersystems/iris/iris.cpf.python_merge
up  IRIS              2024.3.0.217.0    1972   /opt/intersystems/iris

Username: SuperUser
Password: ***
IRIS Merge of /opt/intersystems/iris/iris.cpf.python_merge into /opt/intersystems/iris/iris.cpf
IRIS Merge completed successfully
INFO:iris_utils._find_libpyton:PythonRuntimeLibrary path set to /usr/local/Cellar/python@3.11/3.11.10/Frameworks/Python.framework/Versions/3.11/Python
INFO:iris_utils._find_libpyton:PythonPath set to /Other/.venv/lib/python3.11/site-packages
INFO:iris_utils._find_libpyton:PythonRuntimeLibraryVersion set to 3.11
```

# Troubleshooting

You may encounter the following error, here is how to fix them.

## No module named 'pythonint'

This can occur when the environment variable `IRISINSTALLDIR` is not set correctly. Make sure that the path is correct.

## IRIS_ACCESSDENIED (-15)

This can occur when the service callin is not enabled. Make sure that the service callin is enabled.

## IRIS_ATTACH (-21)

This can occur when the user is not the same as the iris owner. Make sure that the user is the same as the iris owner.