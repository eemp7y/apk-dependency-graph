"""Командная строка анализа зависимостей пакетов Alpine Linux."""

import argparse
from dataclasses import asdict
from pathlib import Path
import sys

from src.config import ConfigError, load_config
from src.graph import analyze_graph
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


def show_graph(config, config_path):
    """Вывести граф и явно обозначить границы глубины и найденные циклы."""
    graph = analyze_graph(config, config_path)
    print(f"Граф зависимостей (максимальная глубина: {config.max_depth}):")
    for node, children in graph.edges.items():
        if graph.depths[node] >= config.max_depth:
            print(f"  {node} [граница глубины]")
        elif children:
            print(f"  {node} -> {', '.join(children)}")
        else:
            print(f"  {node} -> нет зависимостей")
    print(f"Всего пакетов: {len(graph.edges)}")
    print("Циклы в построенном графе:")
    if not graph.cycles:
        print("  не обнаружены")
    for cycle in graph.cycles:
        print(f"  {' -> '.join(cycle)}")


def parse_arguments(argv):
    """Разобрать путь конфигурации и взаимоисключающие режимы вывода."""
    parser = argparse.ArgumentParser(description="Анализ зависимостей apk")
    parser.add_argument(
        "--config", type=Path, default=DEFAULT_CONFIG,
        help="Путь к YAML-файлу настроек",
    )
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument(
        "--show-config", action="store_true",
        help="Только вывести настройки (этап 1), без обращения к сети",
    )
    modes.add_argument(
        "--direct", action="store_true",
        help="Только прямые зависимости из Alpine (этап 2)",
    )
    return parser.parse_args(argv)


def main(argv=None):
    """Построить граф или повторить ранние этапы; вернуть код ошибки."""
    args = parse_arguments(argv)
    try:
        config = load_config(args.config)
    except ConfigError as error:
        print(f"Ошибка конфигурации: {error}", file=sys.stderr)
        return 1
    try:
        if args.show_config:
            show_config(config)
        elif args.direct:
            show_dependencies(config)
        else:
            show_graph(config, args.config)
    except RepositoryError as error:
        print(f"Ошибка репозитория: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
