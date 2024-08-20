# iris-embedded-python-wrapper
Embedded Python Wrapper for venv

# Pre-requisites

Set the following environment variables:

```bash
export IRISINSTALLDIR=/opt/iris
export LD_LIBRARY_PATH=$IRISINSTALLDIR/bin:$LD_LIBRARY_PATH
# for MacOS
export DYLD_LIBRARY_PATH=$IRISINSTALLDIR/bin:$DYLD_LIBRARY_PATH
```

For windows :
    
```bash
set IRISINSTALLDIR=C:\path\to\iris
set LD_LIBRARY_PATH=%IRISINSTALLDIR%\bin;%LD_LIBRARY_PATH%
```

Update the library path for windows

```bash
set PATH=%IRISINSTALLDIR%\bin;%PATH%
```

# Installation  

```bash
pip install iris-embedded-python-wrapper
```
