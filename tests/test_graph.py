"""DFS, общие зависимости, циклы, глубина и тестовые файлы."""

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from src.config import Config, load_config
from src.graph import analyze_graph, build_graph
from src.main import main
from src.repository import RepositoryError
from src.test_repository import load_test_repository


PROJECT = Path(__file__).resolve().parent.parent


def alphabetic_name(number):
    """Имена A-Z, AA-ZZ и далее для длинного учебного графа."""
    result = ""
    while number:
        number, digit = divmod(number - 1, 26)
        result = chr(ord("A") + digit) + result
    return result


class GraphTests(unittest.TestCase):
    """Проверки алгоритма на разных формах графа."""

    def test_chain_and_depth(self):
        """Корень имеет глубину 0, граница не раскрывается."""
        source = {"A": ("B",), "B": ("C",), "C": ()}
        for depth, expected in [(0, {"A"}), (1, {"A", "B"}),
                                (2, {"A", "B", "C"})]:
            with self.subTest(depth=depth):
                graph = build_graph("A", source.__getitem__, depth)
                self.assertEqual(set(graph.edges), expected)
        self.assertEqual(build_graph("A", source.__getitem__, 1)
                         .edges["B"], ())

    def test_shared_dependency_is_not_cycle(self):
        """Ромб содержит четыре узла, общее ребро не считается циклом."""
        source = {"A": ("B", "C"), "B": ("D",), "C": ("D",), "D": ()}
        calls = []

        def dependencies(node):
            """Запомнить раскрываемые узлы."""
            calls.append(node)
            return source[node]

        graph = build_graph("A", dependencies, 3)
        self.assertEqual(graph.cycles, [])
        self.assertEqual(calls, ["A", "B", "D", "C"])
        self.assertEqual(graph.edges["C"], ("D",))

    def test_shorter_path_reopens_boundary(self):
        """После длинного пути к D короткий путь позволяет раскрыть E."""
        source = {
            "A": ("B", "D"), "B": ("C",), "C": ("D",),
            "D": ("E",), "E": ("F",), "F": (),
        }
        graph = build_graph("A", source.__getitem__, 3)
        self.assertEqual(graph.edges["D"], ("E",))
        self.assertEqual(graph.edges["E"], ("F",))
        self.assertEqual(graph.depths["D"], 1)
        self.assertEqual(graph.depths["F"], 3)

    def test_shorter_path_reopens_expanded_node(self):
        """Повторное раскрытие обновляет глубины уже найденных потомков."""
        source = {
            "A": ("B", "D"), "B": ("C",), "C": ("D",),
            "D": ("E",), "E": ("F",), "F": ("G",), "G": (),
        }
        graph = build_graph("A", source.__getitem__, 4)
        self.assertIn("G", graph.edges)
        self.assertEqual(graph.depths["E"], 2)

    def test_cycle(self):
        """Цикл сохраняется в графе и не приводит к бесконечному обходу."""
        source = {"A": ("B",), "B": ("C",), "C": ("A", "D"), "D": ()}
        graph = build_graph("A", source.__getitem__, 10)
        self.assertEqual(graph.cycles, [("A", "B", "C", "A")])
        self.assertEqual(set(graph.edges), set(source))

    def test_self_cycle(self):
        """Ссылка пакета на самого себя обнаруживается."""
        graph = build_graph("A", lambda node: ["A"], 3)
        self.assertEqual(graph.cycles, [("A", "A")])

    def test_cycle_outside_depth_is_not_reported(self):
        """Рёбра за границей не читаются и не порождают ложных выводов."""
        source = {"A": ("B",), "B": ("A",)}
        graph = build_graph("A", source.__getitem__, 1)
        self.assertEqual(graph.cycles, [])

    def test_deep_graph_is_not_recursive(self):
        """Цепочка длиннее лимита рекурсии обрабатывается стеком."""
        names = [alphabetic_name(i) for i in range(1, 1502)]
        source = {a: (b,) for a, b in zip(names, names[1:])}
        source[names[-1]] = ()
        graph = build_graph(names[0], source.__getitem__, len(names))
        self.assertEqual(len(graph.edges), len(names))
        self.assertEqual(graph.cycles, [])

    def test_duplicate_edges(self):
        """Дубликаты зависимостей не создают повторные рёбра."""
        source = {"A": ("B", "B"), "B": ()}
        self.assertEqual(build_graph("A", source.__getitem__, 3)
                         .edges["A"], ("B",))

    def test_invalid_depth(self):
        """Алгоритм сам проверяет глубину при прямом вызове."""
        for value in [-1, True, "3"]:
            with self.subTest(value=value):
                with self.assertRaises(RepositoryError):
                    build_graph("A", lambda node: (), value)


class TestRepositoryTests(unittest.TestCase):
    """Валидация учебного YAML и интеграция командной строки."""

    def setUp(self):
        """Создать временный локальный репозиторий."""
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "repository.yaml"

    def test_invalid_files(self):
        """Проверяются имена, типы, синтаксис и висячие зависимости."""
        for text in ["a: []", "A: B", "A: [b]", "A: [B]",
                     "A: [1]", "A: [", "- A", "A: [true]"]:
            with self.subTest(text=text):
                self.path.write_text(text, encoding="utf-8")
                with self.assertRaises(RepositoryError):
                    load_test_repository(self.path)

    def test_missing_root(self):
        """Отсутствующий стартовый пакет даёт ошибку."""
        config_path = PROJECT / "examples/config-test.yaml"
        config = replace(load_config(config_path), package_name="Z")
        with self.assertRaisesRegex(RepositoryError, "не найден"):
            analyze_graph(config, config_path)

    def test_relative_path_and_no_network(self):
        """Путь считается от конфигурации, а не рабочей папки."""
        config_path = PROJECT / "examples/config-test.yaml"
        with patch("src.graph.download_index") as downloader:
            graph = analyze_graph(load_config(config_path), config_path)
        downloader.assert_not_called()
        self.assertEqual(set(graph.edges), {"A", "B", "C", "D"})

    def test_cli_cycle(self):
        """В командной строке виден путь цикла."""
        output = io.StringIO()
        path = str(PROJECT / "examples/config-cycle.yaml")
        with redirect_stdout(output):
            code = main(["--config", path])
        self.assertEqual(code, 0)
        self.assertIn("A -> B -> C -> A", output.getvalue())

    def test_cli_zero(self):
        """На глубине 0 выводится только корень с отметкой границы."""
        output = io.StringIO()
        path = str(PROJECT / "examples/config-zero.yaml")
        with redirect_stdout(output):
            self.assertEqual(main(["--config", path]), 0)
        self.assertIn("A [граница глубины]", output.getvalue())
        self.assertIn("Всего пакетов: 1", output.getvalue())

    def test_cli_empty(self):
        """Граф из одного пакета выводится как пакет без зависимостей."""
        output = io.StringIO()
        path = str(PROJECT / "examples/config-empty.yaml")
        with redirect_stdout(output):
            self.assertEqual(main(["--config", path]), 0)
        self.assertIn("A -> нет зависимостей", output.getvalue())

    def test_cli_analysis_error(self):
        """Ошибка анализа превращается в ненулевой код завершения."""
        output = io.StringIO()
        with patch("src.main.analyze_graph", side_effect=RepositoryError("x")):
            with redirect_stderr(output):
                self.assertEqual(main([]), 1)
        self.assertIn("Ошибка репозитория: x", output.getvalue())


if __name__ == "__main__":
    unittest.main()
