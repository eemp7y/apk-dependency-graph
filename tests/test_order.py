"""Порядок зависимостей, циклы и ограничения глубины."""

from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path
import unittest

from src.graph import Graph, build_graph
from src.main import main
from src.order import loading_order
from src.repository import RepositoryError


PROJECT = Path(__file__).resolve().parent.parent


class LoadingOrderTests(unittest.TestCase):
    """Топологические свойства, а не только конкретная форма вывода."""

    def assert_dependencies_first(self, graph, order):
        """Каждый узел встречается один раз и позже своих зависимостей."""
        self.assertEqual(set(order), set(graph.edges))
        self.assertEqual(len(order), len(graph.edges))
        positions = {node: i for i, node in enumerate(order)}
        for node, children in graph.edges.items():
            for child in children:
                self.assertLess(positions[child], positions[node])

    def test_chain(self):
        """Порядок цепочки начинается с её последней зависимости."""
        source = {"A": ("B",), "B": ("C",), "C": ()}
        graph = build_graph("A", source.__getitem__, 4)
        result = loading_order(graph)
        self.assertEqual(result, ["C", "B", "A"])
        self.assert_dependencies_first(graph, result)

    def test_shared_dependency(self):
        """Общая зависимость ромба загружается один раз."""
        source = {"A": ("C", "B"), "B": ("D",), "C": ("D",), "D": ()}
        graph = build_graph("A", source.__getitem__, 3)
        result = loading_order(graph)
        self.assertEqual(result, ["D", "B", "C", "A"])
        self.assert_dependencies_first(graph, result)

    def test_deterministic_independent_nodes(self):
        """Перестановка входных записей не меняет результат."""
        first = Graph({"B": (), "A": (), "C": ("B", "A")}, {}, [])
        second = Graph({"C": ("A", "B"), "A": (), "B": ()}, {}, [])
        self.assertEqual(loading_order(first), loading_order(second))
        self.assert_dependencies_first(first, loading_order(first))

    def test_cycle(self):
        """При цикле строгий порядок не выдумывается."""
        source = {"A": ("B",), "B": ("A",)}
        graph = build_graph("A", source.__getitem__, 3)
        with self.assertRaisesRegex(RepositoryError, "A -> B -> A"):
            loading_order(graph)

    def test_self_cycle(self):
        """Самозависимость также делает порядок невозможным."""
        graph = Graph({"A": ("A",)}, {}, [])
        with self.assertRaisesRegex(RepositoryError, "A -> A"):
            loading_order(graph)

    def test_cycle_and_independent_leaf(self):
        """Наличие готового листа не скрывает цикл в другой ветви."""
        graph = Graph({"A": ("B",), "B": ("A",), "C": ()}, {}, [])
        with self.assertRaisesRegex(RepositoryError, "цикл"):
            loading_order(graph)

    def test_missing_dependency(self):
        """Некорректный граф даёт понятную ошибку вместо KeyError."""
        with self.assertRaisesRegex(RepositoryError, "неописанные"):
            loading_order(Graph({"A": ("B",)}, {}, []))

    def test_empty_graph_and_single_node(self):
        """Пустой граф и один независимый пакет обрабатываются."""
        self.assertEqual(loading_order(Graph({}, {}, [])), [])
        self.assertEqual(loading_order(Graph({"A": ()}, {}, [])), ["A"])

    def test_duplicate_edges(self):
        """Дубликат ребра не оставляет пакет в ожидании навсегда."""
        graph = Graph({"A": ("B", "B"), "B": ()}, {}, [])
        self.assertEqual(loading_order(graph), ["B", "A"])

    def test_deep_graph(self):
        """Сортировка длинной цепочки не зависит от лимита рекурсии."""
        size = 1501
        edges = {str(i): (str(i + 1),) for i in range(size - 1)}
        edges[str(size - 1)] = ()
        graph = Graph(edges, {}, [])
        result = loading_order(graph)
        self.assert_dependencies_first(graph, result)
        self.assertEqual(result[0], str(size - 1))

    def test_cli_test_graph(self):
        """В учебном ромбе получается D, B, C, A без предупреждения."""
        output = io.StringIO()
        path = str(PROJECT / "examples/config-test.yaml")
        with redirect_stdout(output):
            code = main(["--order", "--config", path])
        self.assertEqual(code, 0)
        self.assertIn("1. D\n  2. B\n  3. C\n  4. A", output.getvalue())
        self.assertNotIn("Внимание", output.getvalue())

    def test_cli_cycle_has_no_partial_success(self):
        """Цикл даёт код 1 и ошибку без частичного списка загрузки."""
        output, errors = io.StringIO(), io.StringIO()
        path = str(PROJECT / "examples/config-cycle.yaml")
        with redirect_stdout(output), redirect_stderr(errors):
            code = main(["--order", "--config", path])
        self.assertEqual(code, 1)
        self.assertEqual(output.getvalue(), "")
        self.assertIn("A -> B -> C -> A", errors.getvalue())

    def test_cli_depth_limit_is_explicit(self):
        """Порядок обрезанного графа помечен как частичный."""
        output = io.StringIO()
        path = str(PROJECT / "examples/config-zero.yaml")
        with redirect_stdout(output):
            code = main(["--order", "--config", path])
        self.assertEqual(code, 0)
        self.assertIn("граница глубины", output.getvalue())
        self.assertIn("только для построенной части", output.getvalue())


if __name__ == "__main__":
    unittest.main()
