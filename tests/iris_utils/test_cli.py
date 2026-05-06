from pathlib import Path
import sys
import pytest
import iris_utils._dynalib as dynalib
from iris_utils._cli import IrisConfigManager, IrisVersion, PythonConfig, python_version_string


@pytest.fixture(autouse=True)
def block_real_iris_merge(monkeypatch):
    def fail_merge(_manager):
        pytest.fail("Unit tests must not run real 'iris merge'")

    monkeypatch.setattr(IrisConfigManager, "_merge_cpf_to_iris", fail_merge)


@pytest.fixture
def mock_env(monkeypatch, tmp_path):
    iris_dir = tmp_path / "iris"
    iris_dir.mkdir()
    cpf_path = iris_dir / "iris.cpf"
    
    test_cpf = """[config]
Version=2024.1
PythonRuntimeLibrary=/path/to/python
PythonPath=/path/to/site-packages
"""
    cpf_path.write_text(test_cpf)

    merge_cpf = iris_dir / "merge.cpf"
    merge_cpf.write_text("[Actions]\n")

    merge_with_settings = iris_dir / "merge_with_settings.cpf"
    merge_with_settings.write_text("""[Actions]
ModifyConfig:PythonPath=tot
""")
    
    monkeypatch.setenv("IRISINSTALLDIR", str(iris_dir))
    monkeypatch.setenv("VIRTUAL_ENV", str(tmp_path / "venv"))
    monkeypatch.delenv("ISC_CPF_MERGE_FILE", raising=False)
    return iris_dir

def test_init(mock_env):
    manager = IrisConfigManager()
    assert manager.installdir == str(mock_env)
    assert manager.cpf_path == Path(mock_env, "iris.cpf")
    assert isinstance(manager.iris_version, IrisVersion)
    assert manager.iris_version.major == 2024
    assert manager.iris_version.minor == 1

def test_get_iris_version(mock_env):
    manager = IrisConfigManager()
    version = manager._get_iris_version()
    assert version.major == 2024
    assert version.minor == 1

def test_make_backup(mock_env):
    manager = IrisConfigManager()
    manager.make_backup()
    backup_file = manager.get_backup_file()
    assert backup_file is not None
    assert Path(backup_file).exists()

def test_update_config_windows(mock_env, monkeypatch):
    monkeypatch.setattr("iris_utils._cli.is_windows", True)

    manager = IrisConfigManager()
    test_lib = "/test/libpython.so"
    
    manager.update_config(test_lib)
    
    with open(manager.cpf_path) as f:
        content = f.read()
        assert f"PythonRuntimeLibrary={test_lib}" in content
        assert "PythonPath=" in content

def test_create_config_linux(mock_env, monkeypatch):
    monkeypatch.setattr("iris_utils._cli.is_windows", False)

    manager = IrisConfigManager()
    test_lib = "/test/libpython.so"
    config = PythonConfig(runtime=test_lib, path=manager.python_path)
    
    manager._create_new_merge_file(config)
    
    # open the merged cpf file
    _merge_file = Path(f"{manager.cpf_path}.{manager._merge_cpf_suffix}")
    with open(_merge_file, "r") as f:
        lines = f.read()
        assert "[Actions]\n" in lines
        assert f"ModifyConfig:PythonRuntimeLibrary={test_lib}" in lines
        assert "ModifyConfig:PythonPath=" in lines

def test_update_config_linux(mock_env, monkeypatch):
    monkeypatch.setattr("iris_utils._cli.is_windows", False)
    monkeypatch.setenv("ISC_CPF_MERGE_FILE", str(mock_env / "merge_with_settings.cpf"))

    manager = IrisConfigManager()
    test_lib = "/test/libpython.so"
    
    manager.update_config(test_lib)
    
    # open the merged cpf file
    _merge_file = Path(mock_env / "merge_with_settings.cpf")
    with open(_merge_file, "r") as f:
        lines = f.read()
        assert "[Actions]\n" in lines
        assert f"ModifyConfig:PythonRuntimeLibrary={test_lib}" in lines
        assert "ModifyConfig:PythonPath=" in lines

def test_old_iris_version(mock_env):
    with open(mock_env / "iris.cpf", "w") as f:
        f.write("[config]\nVersion=2023.1\n")
    
    manager = IrisConfigManager()
    with pytest.raises(RuntimeError, match="IRIS version must be 2024.1 or higher"):
        manager.update_config("/test/lib")

def test_missing_installdir(monkeypatch):
    monkeypatch.delenv("IRISINSTALLDIR", raising=False)
    monkeypatch.delenv("ISC_PACKAGE_INSTALLDIR", raising=False)
    
    with pytest.raises(EnvironmentError, match="IRISINSTALLDIR environment variable must be set"):
        IrisConfigManager()


def test_requires_python_version_for_2025_1():
    assert IrisVersion(2025, 1).requires_python_version is True


def test_python_version_string_uses_major_minor_only():
    assert python_version_string() == f"{sys.version_info.major}.{sys.version_info.minor}"


def test_get_python_path_uses_major_minor_only(mock_env):
    manager = IrisConfigManager()
    assert manager.python_path.endswith(f"lib/python{python_version_string()}/site-packages")


def test_update_dynalib_path_windows_adds_dll_directory(monkeypatch):
    dynalib_path = r"C:\InterSystems\IRIS\bin"
    calls = []
    handles = []

    def fake_add_dll_directory(path):
        calls.append(path)
        handle = object()
        handles.append(handle)
        return handle

    monkeypatch.setattr(dynalib.sys, "platform", "win32")
    monkeypatch.setattr(dynalib.os, "add_dll_directory", fake_add_dll_directory, raising=False)
    monkeypatch.setattr(dynalib, "_DLL_DIRECTORY_HANDLES", [])
    monkeypatch.setattr(dynalib, "_DLL_DIRECTORY_PATHS", set())
    monkeypatch.setenv("PATH", r"C:\Windows")

    dynalib.update_dynalib_path(dynalib_path)
    dynalib.update_dynalib_path(dynalib_path)

    assert calls == [dynalib_path]
    assert dynalib._DLL_DIRECTORY_HANDLES == handles
    assert dynalib_path in dynalib.os.environ["PATH"]
