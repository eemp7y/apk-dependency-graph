"""Интерпретация сравнения с эталоном без Docker в модульных тестах."""

import unittest

from src.graph import Graph
from tools.compare_apk import compare_order


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


if __name__ == "__main__":
    unittest.main()
