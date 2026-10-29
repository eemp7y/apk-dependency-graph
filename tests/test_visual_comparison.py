"""Сравнение рёбер визуализаций без Docker и Graphviz."""

import unittest

from src.graph import Graph
from src.repository import Package
from tools.compare_visualization import (
    all_provider_graph, compare_edges, compare_with_alternatives,
    parse_dot_edges,
)


class VisualComparisonTests(unittest.TestCase):
    """Рёбра сравниваются по именам и версиям, а не координатам рисунка."""

    def test_apk_labels_and_duplicates(self):
        """Имена с дефисами нормализуются, повторное ребро удаляется."""
        packages = [Package("busybox-binsh", "1.0-r0", ()),
                    Package("musl", "2.0-r1", ())]
        text = ('"busybox-binsh-1.0-r0" -> "musl-2.0-r1";\n' * 2)
        self.assertEqual(parse_dot_edges(text, packages),
                         {("busybox-binsh@1.0-r0", "musl@2.0-r1")})

    def test_unknown_node(self):
        """Неизвестный узел эталона не исчезает из сравнения молча."""
        with self.assertRaises(RuntimeError):
            parse_dot_edges('"unknown" -> "other";', [])

    def test_equal_topology(self):
        """Порядок перечисления рёбер не влияет на равенство."""
        graph = Graph({"A": ("B", "C"), "B": (), "C": ()}, {}, [])
        result = compare_edges(graph, {("A", "C"), ("A", "B")})
        self.assertTrue(result["same_edges"])
        self.assertEqual(result["our_edges"], 2)

    def test_missing_and_extra_edges(self):
        """Отсутствующие и лишние рёбра перечисляются явно."""
        graph = Graph({"A": ("B",), "B": ()}, {}, [])
        result = compare_edges(graph, {("B", "A")})
        self.assertFalse(result["same_edges"])
        self.assertEqual(result["only_ours"], [("A", "B")])
        self.assertEqual(result["only_apk"], [("B", "A")])

    def test_all_provider_model(self):
        """Модель apk dot включает альтернативы и их потомков."""
        root = Package("app", "1", ("virtual>=1",))
        first = Package("first", "1", (), ("virtual=1",), 100)
        second = Package("second", "2", ("leaf",), ("virtual=2",))
        leaf = Package("leaf", "1", ())
        graph = all_provider_graph([root, first, second, leaf], root)
        self.assertEqual(graph.edges["app@1"], ("first@1", "second@2"))
        self.assertEqual(graph.edges["second@2"], ("leaf@1",))

    def test_only_verified_alternatives_are_accepted(self):
        """Необъяснённое ребро не принимается за вариант поставщика."""
        selected = Graph({"A": ("B",), "B": ()}, {}, [])
        expanded = Graph({"A": ("B", "C"), "B": (), "C": ()}, {}, [])
        reference = {("A", "B"), ("A", "C")}
        result = compare_with_alternatives(selected, expanded, reference)
        self.assertTrue(result["explained_provider_alternatives"])
        result = compare_with_alternatives(
            selected, expanded, reference | {("C", "B")},
        )
        self.assertFalse(result["explained_provider_alternatives"])


if __name__ == "__main__":
    unittest.main()
