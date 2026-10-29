"""Сопоставление зависимостей реальным пакетам и их provides."""

from collections import defaultdict
from functools import cmp_to_key
import re

from src.repository import RepositoryError
from src.versions import compare_versions, matches_version


DEPENDENCY_PATTERN = re.compile(r"([^<>=~\s]+)(?:([<>=~]+)([0-9][^\s]*))?")


def parse_dependency(text):
    """Разделить имя зависимости, оператор и версию."""
    match = DEPENDENCY_PATTERN.fullmatch(text)
    if not match or text.startswith("!"):
        raise RepositoryError(f"Некорректная зависимость: {text}")
    name, operation, version = match.groups()
    if operation and not version:
        raise RepositoryError(f"Не задана версия зависимости: {text}")
    return name, operation or "", version or ""


def package_label(package):
    """Создать однозначную метку узла с версией."""
    return f"{package.name}@{package.version}"


class Resolver:
    """Индекс имён и поставщиков виртуальных зависимостей."""

    def __init__(self, packages, root):
        """Один раз индексировать репозиторий и закрепить версию корня."""
        self.entries = defaultdict(list)
        self.root = root
        self.cache = {}
        for package in packages:
            self.entries[package.name].append((package, package.version))
            for provided in package.provides:
                name, separator, version = provided.partition("=")
                self.entries[name].append(
                    (package, version if separator else None)
                )

    def resolve(self, dependency):
        """Выбрать удовлетворяющий ограничению пакет или сообщить ошибку."""
        if dependency in self.cache:
            return self.cache[dependency]
        name, operation, version = parse_dependency(dependency)
        candidates = []
        for package, provided_version in self.entries[name]:
            if package.name == self.root.name and package != self.root:
                continue
            if matches_version(provided_version, operation, version):
                candidates.append(package)
        if not candidates:
            raise RepositoryError(
                f"Не найден поставщик зависимости {dependency}. "
                "Проверьте выбранный репозиторий."
            )
        selected = choose_candidate(candidates, name)
        self.cache[dependency] = selected
        return selected


def choose_candidate(candidates, name):
    """Предпочесть собственное имя, затем приоритет; не гадать при ничьей."""
    direct = [package for package in candidates if package.name == name]
    candidates = direct or candidates
    priority = max(package.provider_priority for package in candidates)
    candidates = [
        package for package in candidates
        if package.provider_priority == priority
    ]
    names = sorted({package.name for package in candidates})
    if len(names) > 1:
        raise RepositoryError(
            f"Неоднозначный поставщик {name}: {', '.join(names)}"
        )
    key = cmp_to_key(
        lambda left, right: compare_versions(left.version, right.version)
    )
    return max(candidates, key=key)
