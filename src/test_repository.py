"""Чтение локальных учебных графов из YAML."""

from pathlib import Path
import re

from src.config import ConfigError, read_mapping
from src.repository import RepositoryError


NAME_PATTERN = re.compile(r"[A-Z]+")


def valid_name(value):
    """Допускать только непустые имена из больших латинских букв."""
    return isinstance(value, str) and NAME_PATTERN.fullmatch(value)


def load_test_repository(path):
    """Прочитать граф, проверить все вершины и ссылки между ними."""
    try:
        data = read_mapping(Path(path))
    except ConfigError as error:
        raise RepositoryError(f"Тестовый репозиторий: {error}") from error
    graph = {}
    for name, dependencies in data.items():
        if not valid_name(name):
            raise RepositoryError("Имена тестовых пакетов: только A-Z.")
        if not isinstance(dependencies, list):
            raise RepositoryError(f"Зависимости {name} должны быть списком.")
        if not all(valid_name(item) for item in dependencies):
            raise RepositoryError(f"Некорректное имя в зависимостях {name}.")
        graph[name] = tuple(dict.fromkeys(dependencies))
    for name, dependencies in graph.items():
        missing = set(dependencies) - graph.keys()
        if missing:
            raise RepositoryError(
                f"У {name} не описаны зависимости: {', '.join(sorted(missing))}"
            )
    return graph
