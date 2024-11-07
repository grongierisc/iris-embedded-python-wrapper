from pathlib import Path
from unittest.mock import MagicMock
import pytest
from iris_utils._cli import IrisConfigManager, IrisVersion

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
    
    monkeypatch.setenv("IRISINSTALLDIR", str(iris_dir))
    monkeypatch.setenv("VIRTUAL_ENV", str(tmp_path / "venv"))
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

def test_update_config_linux(mock_env, monkeypatch):
    monkeypatch.setattr("iris_utils._cli.is_windows", False)

    manager = IrisConfigManager()
    manager._get_iris_instance_name = MagicMock(return_value="IRIS")
    test_lib = "/test/libpython.so"
    
    manager.update_config(test_lib)
    
    # open the merged cpf file
    _merge_file = Path(f"{manager.cpf_path}.{manager._merge_cpf_suffix}")
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