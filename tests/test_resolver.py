"""Разрешение имён, виртуальных зависимостей и ограничений версий."""

import unittest
from unittest.mock import patch

from src.config import Config
from src.graph import analyze_alpine_graph
from src.repository import Package, RepositoryError
from src.resolver import Resolver, parse_dependency
from src.versions import compare_versions, matches_version


class VersionTests(unittest.TestCase):
    """Числовые части, суффиксы, ревизии и префиксы Alpine."""

    def test_ordering(self):
        """Сравнение числовое и учитывает предварительные релизы."""
        pairs = [
            ("1.9", "1.10"), ("1.0-r2", "1.0-r10"),
            ("1.0_alpha", "1.0_beta"), ("1.0_pre", "1.0_rc1"),
            ("1.0_rc1", "1.0"), ("1.0", "1.0_p1"),
            ("1.0", "1.0.0"), ("1.0a", "1.0b"),
            ("1.01", "1.1"), ("1.0_git1", "1.0_git2"),
            ("1.0~abc", "1.0~abd"), ("1.0_p1", "1.0_p2"),
        ]
        for left, right in pairs:
            with self.subTest(left=left, right=right):
                self.assertLess(compare_versions(left, right), 0)
                self.assertGreater(compare_versions(right, left), 0)
        self.assertEqual(compare_versions("1.2-r1", "1.2-r1"), 0)

    def test_constraints(self):
        """Операторы сравнения применяются к фактической версии."""
        cases = [
            ("1.2.3-r1", "~", "1.2", True),
            ("1.20", "~", "1.2", False),
            ("1.2.3", "=~", "1.2", True),
            ("1.2", ">=", "1.2", True),
            ("1.2", ">", "1.2", False),
            ("1.2", "<=", "1.3", True),
            ("1.2", "=", "1.3", False),
            ("1.2", "<~", "1.2", True),
            ("1.3", ">~", "1.2", True),
            (None, ">=", "1", False),
        ]
        for actual, operation, required, expected in cases:
            with self.subTest(actual=actual, operation=operation):
                self.assertEqual(
                    matches_version(actual, operation, required), expected,
                )

    def test_invalid_versions_and_operators(self):
        """Неизвестные форматы не сравниваются молча как строки."""
        for version in ["", "hello", "1.0_unknown", "1..2"]:
            with self.assertRaises(RepositoryError):
                compare_versions(version, "1")
        with self.assertRaises(RepositoryError):
            matches_version("1", "><", "1")


class ResolverTests(unittest.TestCase):
    """Выбор реальных пакетов из учебного индекса."""

    def setUp(self):
        """Подготовить корень и несколько возможных версий зависимости."""
        self.root = Package("app", "1", ("lib>=1",))
        self.lib_old = Package("lib", "1.9", ())
        self.lib_new = Package("lib", "1.10", ())

    def test_latest_matching_version(self):
        """Выбор версии соблюдает ограничение, а не порядок записей."""
        resolver = Resolver([self.root, self.lib_new, self.lib_old], self.root)
        self.assertEqual(resolver.resolve("lib<1.10"), self.lib_old)
        self.assertEqual(resolver.resolve("lib>=1"), self.lib_new)

    def test_virtual_and_versioned_provides(self):
        """so: сопоставляется поставщику; версия берётся из provides."""
        musl = Package("musl", "1.2.5", (), ("so:libc.so=1", "libc"))
        resolver = Resolver([self.root, musl], self.root)
        self.assertEqual(resolver.resolve("so:libc.so>=1"), musl)
        self.assertEqual(resolver.resolve("libc"), musl)
        with self.assertRaises(RepositoryError):
            resolver.resolve("so:libc.so>=2")
        with self.assertRaises(RepositoryError):
            resolver.resolve("libc>=1")

    def test_ambiguous_provider(self):
        """При равном приоритете разных поставщиков выдаётся ошибка."""
        first = Package("first", "1", (), ("virtual",))
        second = Package("second", "2", (), ("virtual",))
        resolver = Resolver([self.root, first, second], self.root)
        with self.assertRaisesRegex(RepositoryError, "Неоднозначный"):
            resolver.resolve("virtual")

    def test_provider_priority(self):
        """Метаданные k позволяют выбрать приоритетного поставщика."""
        first = Package("first", "1", (), ("virtual",), 10)
        second = Package("second", "2", (), ("virtual",), 0)
        resolver = Resolver([self.root, first, second], self.root)
        self.assertEqual(resolver.resolve("virtual"), first)

    def test_direct_name_preferred(self):
        """Собственное имя пакета предпочтительнее виртуального."""
        alias = Package("alias", "2", (), ("lib=2",), 100)
        resolver = Resolver([self.root, self.lib_old, alias], self.root)
        self.assertEqual(resolver.resolve("lib"), self.lib_old)

    def test_root_version_is_pinned(self):
        """Обратная зависимость не подменяет заданную версию корня."""
        newer = Package("app", "2", ())
        resolver = Resolver([newer, self.root], self.root)
        self.assertEqual(resolver.resolve("app>=1"), self.root)
        with self.assertRaises(RepositoryError):
            resolver.resolve("app>=2")

    def test_missing_provider(self):
        """Отсутствие поставщика не создаёт фиктивный лист графа."""
        resolver = Resolver([self.root], self.root)
        with self.assertRaisesRegex(RepositoryError, "Не найден"):
            resolver.resolve("missing")

    def test_invalid_dependency(self):
        """Неполная запись ограничения отклоняется."""
        for text in ["", "!masked", "lib>=", "bad name"]:
            with self.assertRaises(RepositoryError):
                parse_dependency(text)

    def test_alpine_graph_downloaded_once(self):
        """Индекс читается один раз, виртуальные рёбра ведут к пакетам."""
        text = (
            "P:app\nV:1\nD:so:libc.so.1\n\n"
            "P:musl\nV:1.2\np:so:libc.so.1=1\n"
        )
        config = Config("app", "https://example.org", False, "1", 3)
        with patch("src.graph.download_index", return_value=b"x") as load:
            with patch("src.graph.unpack_index", return_value=text):
                graph = analyze_alpine_graph(config)
        load.assert_called_once_with(config.repository)
        self.assertEqual(graph.edges["app@1"], ("musl@1.2",))


if __name__ == "__main__":
    unittest.main()
