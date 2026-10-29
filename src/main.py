"""Командная строка анализа зависимостей пакетов Alpine Linux."""

import argparse
from dataclasses import asdict
from pathlib import Path
import sys

from src.config import ConfigError, load_config
from src.repository import RepositoryError, get_package


DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "config.yaml"


def show_config(config):
    """Вывести пять настроек, как требуется на первом этапе."""
    for key, value in asdict(config).items():
        if isinstance(value, bool):
            value = str(value).lower()
        print(f"{key}: {value}")


def show_dependencies(config):
    """Вывести прямые зависимости указанной версии пакета."""
    package = get_package(config)
    print(f"Пакет: {package.name}")
    print(f"Версия: {package.version}")
    print("Прямые зависимости:")
    if not package.dependencies:
        print("  нет")
    for dependency in package.dependencies:
        print(f"  {dependency}")


def main(argv=None):
    """Вывести зависимости или настройки; при ошибке вернуть код 1."""
    parser = argparse.ArgumentParser(description="Анализ зависимостей apk")
    parser.add_argument(
        "--config", type=Path, default=DEFAULT_CONFIG,
        help="Путь к YAML-файлу настроек",
    )
    parser.add_argument(
        "--show-config", action="store_true",
        help="Только вывести настройки (этап 1), без обращения к сети",
    )
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
    except ConfigError as error:
        print(f"Ошибка конфигурации: {error}", file=sys.stderr)
        return 1
    try:
        if args.show_config:
            show_config(config)
        else:
            show_dependencies(config)
    except RepositoryError as error:
        print(f"Ошибка репозитория: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
