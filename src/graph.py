"""Построение графа итеративным DFS и обнаружение циклов."""

from dataclasses import dataclass
from pathlib import Path

from src.repository import (
    RepositoryError, download_index, find_package, parse_index, unpack_index,
)
from src.resolver import Resolver, package_label
from src.test_repository import load_test_repository


@dataclass
class Graph:
    """Граф, минимальные глубины и обнаруженные обратные рёбра циклов."""

    edges: dict[str, tuple[str, ...]]
    depths: dict[str, int]
    cycles: list[tuple[str, ...]]


def build_graph(root, dependencies, max_depth):
    """Обойти граф стеком; повторно раскрыть узел при более коротком пути."""
    if type(max_depth) is not int or max_depth < 0:
        raise RepositoryError("Глубина должна быть целым числом от 0.")
    stack = [(root, 0)]
    depths, edges, cache = {}, {}, {}
    while stack:
        node, depth = stack.pop()
        if node in depths and depths[node] <= depth:
            continue
        depths[node] = depth
        edges.setdefault(node, ())
        if depth >= max_depth:
            continue
        if node not in cache:
            cache[node] = tuple(dict.fromkeys(dependencies(node)))
        edges[node] = cache[node]
        for child in reversed(edges[node]):
            stack.append((child, depth + 1))
    return Graph(edges, depths, find_cycles(edges))


def find_cycles(edges):
    """Найти обратные рёбра отдельным DFS со стеком активного пути."""
    finished, cycles = set(), []
    for root in edges:
        if root in finished:
            continue
        path, active = [root], {root: 0}
        stack = [(root, iter(edges[root]))]
        while stack:
            node, children = stack[-1]
            child = next(children, None)
            if child is None:
                stack.pop()
                finished.add(node)
                active.pop(node)
                path.pop()
            elif child in active:
                cycles.append(tuple(path[active[child]:] + [child]))
            elif child not in finished:
                active[child] = len(path)
                path.append(child)
                stack.append((child, iter(edges[child])))
    return cycles


def analyze_test_graph(config, config_path):
    """Разобрать тестовый файл; его пути считаются от YAML-конфигурации."""
    path = Path(config.repository)
    if not path.is_absolute():
        path = Path(config_path).resolve().parent / path
    repository = load_test_repository(path)
    if config.package_name not in repository:
        raise RepositoryError(f"Пакет {config.package_name} не найден.")
    return build_graph(
        config.package_name, repository.__getitem__, config.max_depth,
    )


def analyze_alpine_graph(config):
    """Скачать индекс один раз и разрешать зависимости через provides."""
    packages = parse_index(unpack_index(download_index(config.repository)))
    root = find_package(packages, config.package_name, config.package_version)
    resolver = Resolver(packages, root)
    known = {package_label(root): root}

    def dependencies(label):
        """Получить пакеты, предоставляющие зависимости конкретного узла."""
        result = []
        for token in known[label].dependencies:
            target = resolver.resolve(token)
            target_label = package_label(target)
            known[target_label] = target
            result.append(target_label)
        return result

    return build_graph(package_label(root), dependencies, config.max_depth)


def analyze_graph(config, config_path):
    """Выбрать источник графа согласно тестовому режиму."""
    if config.test_mode:
        return analyze_test_graph(config, config_path)
    return analyze_alpine_graph(config)
