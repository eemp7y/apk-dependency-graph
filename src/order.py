"""Порядок загрузки: зависимости раньше использующих их пакетов."""

from collections import defaultdict
import heapq

from src.graph import find_cycles
from src.repository import RepositoryError


def loading_order(graph):
    """Топологически упорядочить граф алгоритмом Кана без рекурсии."""
    pending = {}
    users = defaultdict(list)
    for node, children in graph.edges.items():
        unique = set(children)
        missing = unique - graph.edges.keys()
        if missing:
            raise RepositoryError("В графе есть неописанные зависимости.")
        pending[node] = len(unique)
        for dependency in sorted(unique):
            users[dependency].append(node)
    ready = [node for node, count in pending.items() if count == 0]
    heapq.heapify(ready)
    result = []
    while ready:
        node = heapq.heappop(ready)
        result.append(node)
        for user in users[node]:
            pending[user] -= 1
            if pending[user] == 0:
                heapq.heappush(ready, user)
    if len(result) != len(graph.edges):
        cycle = " -> ".join(find_cycles(graph.edges)[0])
        raise RepositoryError(
            f"Порядок загрузки невозможен: обнаружен цикл {cycle}."
        )
    return result
