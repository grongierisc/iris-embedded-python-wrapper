#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${IRIS_APP_DIR:-/irisdev/app}"
VENV_DIR="${PYTEST_VENV_DIR:-/tmp/iris-wrapper-pytest-venv}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
IRIS_INSTALL_DIR="${IRISINSTALLDIR:-${ISC_PACKAGE_INSTALLDIR:-/usr/irissys}}"

export IRISINSTALLDIR="${IRISINSTALLDIR:-$IRIS_INSTALL_DIR}"
export LD_LIBRARY_PATH="${IRIS_INSTALL_DIR}/bin${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export PYTHONPATH="${APP_DIR}${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONDONTWRITEBYTECODE=1
export PYTEST_ADDOPTS="${PYTEST_ADDOPTS:+$PYTEST_ADDOPTS }-p no:cacheprovider"

cd "$APP_DIR"

# Keep tests from rewriting the repository-level merge file mounted into IRIS.
unset ISC_CPF_MERGE_FILE

"$PYTHON_BIN" -m venv --clear "$VENV_DIR"
# shellcheck disable=SC1091
. "$VENV_DIR/bin/activate"

python3 -m pip install --upgrade pip setuptools wheel
python3 - <<'PY'
import subprocess
import sys

try:
    import tomllib
except ModuleNotFoundError as exc:
    raise RuntimeError("Python 3.11+ is required to read pyproject.toml in this test runner") from exc

with open("pyproject.toml", "rb") as pyproject_file:
    dependencies = tomllib.load(pyproject_file).get("project", {}).get("dependencies", [])

if dependencies:
    subprocess.check_call([sys.executable, "-m", "pip", "install", *dependencies])
PY
python3 -m pip install pytest

export IRIS_HOST="${IRIS_HOST:-localhost}"
export IRIS_PORT="${IRIS_PORT:-1972}"
export IRISNAMESPACE="${IRISNAMESPACE:-USER}"
export IRISUSERNAME="${IRISUSERNAME:-_SYSTEM}"
export IRISPASSWORD="${IRISPASSWORD:-SYS}"
export IRIS_E2E_MODES="${IRIS_E2E_MODES:-embedded,remote}"
export IRIS_REQUIRE_EMBEDDED="${IRIS_REQUIRE_EMBEDDED:-1}"
export IRIS_REQUIRE_EMBEDDED_SQL="${IRIS_REQUIRE_EMBEDDED_SQL:-1}"
export IRIS_RUN_KERNEL_TEST="${IRIS_RUN_KERNEL_TEST:-1}"

exec python3 -m pytest "$@"
