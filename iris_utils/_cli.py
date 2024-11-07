import os
import sys
import argparse
import hashlib
import shutil
from dataclasses import dataclass
from typing import Optional, Dict, List
from pathlib import Path

from ._find_libpyton import find_libpython, is_windows, logger

@dataclass
class IrisVersion:
    major: int
    minor: int

    @property
    def requires_python_version(self) -> bool:
        return self.major >= 2024 and self.minor >= 2

@dataclass
class PythonConfig:
    runtime: str
    path: str
    version: Optional[str] = None

    def to_config_lines(self) -> Dict[str, str]:
        config = {
            'runtime': f"PythonRuntimeLibrary={self.runtime}\n",
            'path': f"PythonPath={self.path}\n"
        }
        if self.version is not None:
            config['version'] = f"PythonRuntimeLibraryVersion={self.version}\n"
        return config
    
    def to_action_lines(self) -> Dict[str, str]:
        config = {
            'runtime': f"ModifyConfig:PythonRuntimeLibrary={self.runtime}\n",
            'path': f"ModifyConfig:PythonPath={self.path}\n"
        }
        if self.version is not None:
            config['version'] =  f"ModifyConfig:PythonRuntimeLibraryVersion={self.version}\n"
        return config

class IrisConfigManager:
    def __init__(self):
        self.installdir = self._find_iris_install_dir()
        self.cpf_path = Path(self.installdir, "iris.cpf")
        self.iris_version = self._get_iris_version()
        self.python_path = self._get_python_path()
        self.backup_suffix = hashlib.md5(self.python_path.encode()).hexdigest()
        self.backup_file = f"{self.cpf_path}.{self.backup_suffix}"
        self._merge_cpf_suffix = "python_merge"

    @staticmethod
    def _find_iris_install_dir() -> str:
        installdir = os.environ.get('IRISINSTALLDIR') or os.environ.get('ISC_PACKAGE_INSTALLDIR')
        if not installdir:
            raise EnvironmentError("IRISINSTALLDIR environment variable must be set")
        return installdir
    
    def _get_iris_instance_name(self) -> str:
        iris_all = os.popen("iris all").read()
        for line in iris_all.split("\n"):
            if self.installdir in line:
                return line.split(">")[1].split()[0]
        raise RuntimeError("Could not determine IRIS instance name")
    
    def _merge_cpf_to_iris(self):
        instance_name = self._get_iris_instance_name()
        merge_file = f"{self.cpf_path}.{self._merge_cpf_suffix}"
        os.system(f"iris merge {instance_name} {merge_file}")

    def _get_iris_version(self) -> IrisVersion:
        version_str = self._read_iris_version()
        if not version_str:
            raise RuntimeError("Could not determine IRIS version")
        major, minor = map(int, version_str.split(".")[:2])
        return IrisVersion(major, minor)

    def _read_iris_version(self) -> Optional[str]:
        with open(self.cpf_path, "r") as f:
            for line in f:
                if line.startswith("Version="):
                    return line.split("=")[1].strip()
        return None

    @staticmethod
    def _get_python_path() -> str:
        if "VIRTUAL_ENV" in os.environ:
            return os.path.join(
                os.environ["VIRTUAL_ENV"],
                "lib", 
                f"python{sys.version[:4]}", 
                "site-packages"
            )
        return ""

    def update_config(self, libpython: str):
        if self.iris_version.major < 2024:
            raise RuntimeError("IRIS version must be 2024.1 or higher")

        config = PythonConfig(
            runtime=libpython,
            path=self.python_path,
            version=sys.version[:4] if self.iris_version.requires_python_version else None
        )

        self.make_backup()
        
        if is_windows:
            self.update_iris_cpf(config)
        else:
            self.update_merge_cpf(config)

    def update_iris_cpf(self, config: PythonConfig):
        try:
            lines = self._read_cpf_lines(self.cpf_path)
            self._update_config_section(lines, config)
            self._write_cpf_content(self.cpf_path, lines)
            self._log_changes(config)
            logger.warning("Please restart IRIS instance to apply changes")
        except Exception as e:
            logger.error(f"Failed to update iris.cpf: {str(e)}")
            raise

    def update_merge_cpf(self, config: PythonConfig):
        merge_file = os.environ.get('ISC_CPF_MERGE_FILE')
        try:
            if not merge_file:
                self._create_new_merge_file(config)
                self._merge_cpf_to_iris()
            else:
                lines = self._read_cpf_lines(merge_file)
                self._update_actions_section(lines, config)
                self._write_cpf_content(merge_file, lines)
        except Exception as e:
            logger.error(f"Failed to update merge file: {str(e)}")
            raise
        self._log_changes(config)

    def _create_new_merge_file(self, config: PythonConfig):
        _merge_file = f"{self.cpf_path}.{self._merge_cpf_suffix}"
        with open(_merge_file, "w") as f:
            f.writelines(self._create_actions_section(config))
        logger.info(f"Created merge file at {_merge_file}")

    def _create_actions_section(self, config: PythonConfig) -> List[str]:
        lines = ["[Actions]\n"]
        lines.extend(config.to_action_lines().values())
        return lines

    def _update_actions_section(self, lines: List[str], config: PythonConfig):
        actions_section = self._get_actions_section(lines)
        action_lines = config.to_action_lines()
        
        if actions_section == len(lines):
            lines.extend(action_lines.values())
        else:
            self._update_existing_actions(lines, actions_section, action_lines)

    def _update_config_section(self, lines: List[str], config: PythonConfig):
        config_section = self._get_config_section(lines)
        config_lines = config.to_config_lines()
        
        if config_section == len(lines):
            lines.extend(config_lines.values())
        else:
            self._update_existing_config(lines, config_section, config_lines)

    @staticmethod
    def _get_actions_section(lines: List[str]) -> int:
        for i, line in enumerate(lines):
            if "[Actions]" in line:
                return i
        lines.append("\n[Actions]\n")
        return len(lines)

    @staticmethod
    def _get_config_section(lines: List[str]) -> int:
        for i, line in enumerate(lines):
            if "[config]" in line.lower():
                return i
        lines.append("\n[config]\n")
        return len(lines)

    def _update_existing_config(self, lines: List[str], config_section: int, config: Dict[str, str]):
        config_keys = self._find_config_keys(lines[config_section:], config_section)
        self._validate_config_keys(config_keys)
        
        for key, line_num in config_keys.items():
            if key in config:
                lines[line_num] = config[key]

    def _update_existing_actions(self, lines: List[str], actions_section: int, action_lines: Dict[str, str]):
        action_keys = self._find_action_keys(lines[actions_section:], actions_section)

        offset = 0
        for key, value in action_lines.items():
            if key in action_keys:
                lines[action_keys[key]+offset] = value
            else:
                lines.insert(actions_section+1, value)
                offset += 1

    def _find_action_keys(self, lines: List[str], offset: int) -> Dict[str, int]:
        keys = {}
        for i, line in enumerate(lines):
            if line.startswith("ModifyConfig:PythonRuntimeLibrary="):
                keys['runtime'] = i + offset
            elif line.startswith("ModifyConfig:PythonPath="):
                keys['path'] = i + offset
            elif line.startswith("ModifyConfig:PythonRuntimeLibraryVersion="):
                keys['version'] = i + offset
        return keys

    def _find_config_keys(self, lines: List[str], offset: int) -> Dict[str, int]:
        keys = {}
        for i, line in enumerate(lines):
            if line.startswith("PythonRuntimeLibrary="):
                keys['runtime'] = i + offset
            elif line.startswith("PythonPath="):
                keys['path'] = i + offset
            elif line.startswith("PythonRuntimeLibraryVersion="):
                keys['version'] = i + offset
        return keys

    def _get_config_keys_values(self, lines: List[str]) -> Dict[str, str]:
        keys = {}
        for _, line in enumerate(lines):
            if line.startswith("PythonRuntimeLibrary="):
                keys['runtime'] = line.split("=")[1].strip()
            elif line.startswith("PythonPath="):
                keys['path'] = line.split("=")[1].strip()
            elif line.startswith("PythonRuntimeLibraryVersion="):
                keys['version'] = line.split("=")[1].strip()
        return keys

    def _validate_config_keys(self, config_keys: Dict[str, int]):
        required_keys = ['runtime', 'path']
        if self.iris_version.requires_python_version:
            required_keys.append('version')

        missing = [k for k in required_keys if k not in config_keys]
        if missing:
            raise RuntimeError(f"Missing required keys: {', '.join(missing)}")

    def _log_changes(self, config: PythonConfig):
        logger.info("PythonRuntimeLibrary path set to %s", config.runtime)
        logger.info("PythonPath set to %s", config.path)
        if config.version is not None:
            logger.info("PythonRuntimeLibraryVersion set to %s", config.version)

    ### Backup and restore methods

    def make_backup(self):
        shutil.copy2(self.cpf_path, self.backup_file)
        logger.info(f"Created backup at {self.backup_file}")

    def get_backup_file(self) -> Optional[str]:
        if os.path.exists(self.backup_file):
            return self.backup_file
        return None
    
    ### File I/O methods

    @staticmethod
    def _read_cpf_lines(filename: str) -> List[str]:
        with open(filename, "r") as f:
            return f.readlines()

    @staticmethod
    def _write_cpf_content(filename: str, lines: List[str]):
        with open(filename, "w") as f:
            f.writelines(lines)

def bind():
    parser = argparse.ArgumentParser()
    parser.add_argument("--namespace", default="")
    args = parser.parse_args()

    libpython = find_libpython()
    if not libpython:
        raise RuntimeError("libpython not found")
    
    config_manager = IrisConfigManager()
    config_manager.update_config(libpython)

def unbind():
    config_manager = IrisConfigManager()
    if backup_file := config_manager.get_backup_file():
        if is_windows:
            shutil.copy2(backup_file, config_manager.cpf_path)
            logger.info("Successfully restored iris.cpf from backup")
            logger.warning("Please restart IRIS instance to apply changes")
        else:
            config = PythonConfig("", "")
            with open(backup_file, "r") as f:
                lines = f.readlines()
                config_dict = config_manager._get_config_keys_values(lines)
                config.runtime = config_dict.get('runtime', "")
                config.path = config_dict.get('path', "")
                if config_manager.iris_version.requires_python_version:
                    config.version = config_dict.get('version', "")

            config_manager.update_merge_cpf(config)
    else:
        logger.warning("Backup file not found")
        if config_manager.iris_version.requires_python_version:
            config = PythonConfig("", "", "")
        else:
            config = PythonConfig("", "")
        if is_windows:
            config_manager.update_iris_cpf(config)
        else:
            config_manager.update_merge_cpf(config)
