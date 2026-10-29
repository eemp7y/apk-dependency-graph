"""Чтение и проверка пользовательских настроек."""

from dataclasses import dataclass
from pathlib import Path
import re
from urllib.parse import urlsplit

import yaml


MIN_DEPTH = 0
PACKAGE_PATTERN = r"[A-Za-z0-9][A-Za-z0-9+_.-]*"


class ConfigError(ValueError):
    """Ошибка конфигурационного файла."""


@dataclass(frozen=True)
class Config:
    """Пять параметров приложения, прошедших проверку."""

    package_name: str
    repository: str
    test_mode: bool
    package_version: str
    max_depth: int


def read_mapping(path):
    """Прочитать YAML-файл с настройками в словарь."""
    try:
        with path.open(encoding="utf-8") as stream:
            data = yaml.safe_load(stream)
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise ConfigError(f"Не удалось прочитать {path}: {error}") from error
    if not isinstance(data, dict):
        raise ConfigError("Конфигурация должна быть YAML-словарём.")
    return data


def require_text(data, name):
    """Получить непустую строку без пробелов по краям."""
    value = data[name]
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{name}: ожидается непустая строка.")
    if value != value.strip():
        raise ConfigError(f"{name}: уберите пробелы по краям.")
    return value


def check_repository(repository, test_mode, config_dir):
    """Проверить URL или существующий файл тестового репозитория."""
    if test_mode:
        candidate = Path(repository)
        if not candidate.is_absolute():
            candidate = config_dir / candidate
        if not candidate.is_file():
            raise ConfigError("repository: тестовый файл не найден.")
        return
    try:
        url = urlsplit(repository)
        valid = url.scheme in ("http", "https") and url.hostname
        port = url.port
    except ValueError as error:
        raise ConfigError("repository: некорректный URL.") from error
    if not valid or any(char.isspace() for char in repository):
        raise ConfigError("repository: ожидается URL http:// или https://.")
    if port == 0:
        raise ConfigError("repository: порт должен быть больше нуля.")


def validate_config(data, config_dir):
    """Проверить ключи, типы и значения всех настроек."""
    expected = set(Config.__dataclass_fields__)
    missing = expected - data.keys()
    extra = data.keys() - expected
    if missing:
        names = ', '.join(sorted(missing))
        raise ConfigError(f"Отсутствуют параметры: {names}")
    if extra:
        names = ', '.join(sorted(str(key) for key in extra))
        raise ConfigError(f"Неизвестные параметры: {names}")
    package = require_text(data, "package_name")
    if not re.fullmatch(PACKAGE_PATTERN, package):
        raise ConfigError("package_name: недопустимое имя пакета.")
    require_text(data, "package_version")
    repository = require_text(data, "repository")
    if type(data["test_mode"]) is not bool:
        raise ConfigError("test_mode: ожидается true или false без кавычек.")
    depth = data["max_depth"]
    if type(depth) is not int or depth < MIN_DEPTH:
        raise ConfigError("max_depth: ожидается целое число от 0.")
    check_repository(repository, data["test_mode"], config_dir)
    return Config(**data)


def load_config(path):
    """Прочитать и проверить конфигурацию по указанному пути."""
    path = Path(path)
    return validate_config(read_mapping(path), path.resolve().parent)
