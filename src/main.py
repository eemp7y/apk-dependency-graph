"""Командная строка анализа зависимостей пакетов Alpine Linux."""

import argparse
from dataclasses import asdict
from pathlib import Path
import sys

from src.config import ConfigError, load_config
from src.graph import analyze_graph
from src.order import loading_order
from src.repository import RepositoryError, get_package
from src.visualization import open_visualization, write_visualization


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
    modes.add_argument(
        "--order", action="store_true",
        help="Порядок загрузки: зависимости перед пакетом (этап 4)",
    )
    modes.add_argument(
        "--visualize", action="store_true", help="Открыть граф Mermaid",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=DEFAULT_CONFIG.parent / "generated",
        help="Папка для graph.mmd и graph.html",
    )
    parser.add_argument(
        "--no-open", action="store_true", help="Не открывать браузер",
    )
    args = parser.parse_args(argv)
    if args.no_open and not args.visualize:
        parser.error("--no-open используется только с --visualize")
    return args


def show_visualization(config, args):
    """Сохранить диаграмму и открыть изображение в браузере."""
    graph = analyze_graph(config, args.config)
    mermaid_path, html_path = write_visualization(
        graph, config.max_depth, args.output_dir,
    )
    print(f"Mermaid: {mermaid_path}")
    print(f"Изображение в браузере: {html_path}")
    if not args.no_open and not open_visualization(html_path):
        print("Откройте HTML-файл вручную в браузере.")


def show_order(config, config_path):
    """Вывести полный или явно обозначенный частичный порядок загрузки."""
    graph = analyze_graph(config, config_path)
    ordered = loading_order(graph)
    if any(depth >= config.max_depth for depth in graph.depths.values()):
        print("Внимание: достигнута граница глубины.")
        print("Порядок только для построенной части графа; за границей")
        print("могут быть дополнительные зависимости и циклы.")
    print("Порядок загрузки (зависимости раньше пакета):")
    for position, package in enumerate(ordered, 1):
        print(f"  {position}. {package}")


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
        elif args.order:
            show_order(config, args.config)
        elif args.visualize:
            show_visualization(config, args)
        else:
            show_graph(config, args.config)
    except RepositoryError as error:
        print(f"Ошибка репозитория: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
