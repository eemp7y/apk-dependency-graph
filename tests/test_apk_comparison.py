"""Интерпретация сравнения с эталоном без Docker в модульных тестах."""

import unittest

from src.graph import Graph
from src.repository import Package
from tools.compare_apk import compare_order, explain_install_if


class ComparisonTests(unittest.TestCase):
    """Допустимые перестановки отделяются от ошибок состава и порядка."""

    def setUp(self):
        """Подготовить две независимые зависимости одного пакета."""
        self.graph = Graph({"A": ("B", "C"), "B": (), "C": ()}, {}, [])
        self.expected = ["B", "C", "A"]

    def test_equal_order(self):
        """Совпавший порядок успешно подтверждается."""
        lines, valid = compare_order(self.graph, self.expected, self.expected)
        self.assertTrue(valid)
        self.assertIn("Same sequence: True", lines)

    def test_independent_branches(self):
        """Другая допустимая последовательность получает объяснение."""
        lines, valid = compare_order(self.graph, self.expected, ["C", "B", "A"])
        self.assertTrue(valid)
        self.assertIn("Only independent branches differ", "\n".join(lines))

    def test_invalid_order(self):
        """Пакет раньше собственной зависимости считается нарушением."""
        _, valid = compare_order(self.graph, self.expected, ["A", "B", "C"])
        self.assertFalse(valid)

    def test_missing_package(self):
        """Отсутствие пакета не принимается за другую топосортировку."""
        lines, valid = compare_order(self.graph, self.expected, ["B", "A"])
        self.assertFalse(valid)
        self.assertIn("Only our graph: ['C']", lines)

    def test_explained_install_if_extra(self):
        """Дополнительный пакет принимается только с объяснением метаданных."""
        packages = [
            Package("A", "1", ("B",)), Package("B", "1", ()),
            Package("C", "1", ("B",), install_if=("A=1", "B")),
        ]
        expected = ["B@1", "A@1"]
        actual = ["B@1", "A@1", "C@1"]
        explained = explain_install_if(packages, expected, actual)
        self.assertIn("C@1", explained)
        graph = Graph({"A@1": ("B@1",), "B@1": ()}, {}, [])
        lines, valid = compare_order(graph, expected, actual, explained)
        self.assertTrue(valid)
        self.assertIn("All apk-only packages explained by install_if.", lines)

    def test_unmet_install_if_not_explained(self):
        """Не выполненное условие не оправдывает лишний пакет."""
        packages = [
            Package("A", "1", ()),
            Package("C", "1", (), install_if=("A>=2",)),
        ]
        result = explain_install_if(packages, ["A@1"], ["A@1", "C@1"])
        self.assertEqual(result, {})

    def test_extra_before_its_dependency_not_explained(self):
        """Дополнение apk также должно идти после собственных зависимостей."""
        packages = [
            Package("A", "1", ()),
            Package("C", "1", ("A",), install_if=("A",)),
        ]
        result = explain_install_if(packages, ["A@1"], ["C@1", "A@1"])
        self.assertEqual(result, {})

    def test_unexplained_extra_fails(self):
        """Неизвестный дополнительный пакет остаётся ошибкой сравнения."""
        _, valid = compare_order(
            self.graph, self.expected, ["B", "C", "A", "D"],
        )
        self.assertFalse(valid)

    def test_explained_extra_does_not_hide_missing_package(self):
        """Объяснение дополнения не скрывает потерю обязательного пакета."""
        _, valid = compare_order(
            self.graph, self.expected, ["B", "A", "D"], {"D": "install_if"},
        )
        self.assertFalse(valid)


if __name__ == "__main__":
    unittest.main()
