"""Mermaid, безопасные подписи, файлы и режим визуализации."""

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

from src.graph import build_graph
from src.main import main
from src.repository import RepositoryError
from src.visualization import (
    graph_metadata, mermaid_label, open_visualization, to_mermaid,
    write_visualization,
)


PROJECT = Path(__file__).resolve().parent.parent


class VisualizationTests(unittest.TestCase):
    """Семантика диаграммы соответствует исходному графу."""

    def setUp(self):
        """Подготовить ромб и временную папку для результатов."""
        source = {"A": ("B", "C"), "B": ("D",), "C": ("D",), "D": ()}
        self.graph = build_graph("A", source.__getitem__, 3)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.output = Path(temporary.name)

    def test_all_nodes_and_edges(self):
        """Подписи, число и направление рёбер полностью сохраняются."""
        text = to_mermaid(self.graph, 3)
        self.assertTrue(text.startswith("flowchart TD\n"))
        nodes = dict(re.findall(r'(n\d+)\["([^"\n]+)"\]', text))
        self.assertEqual(set(nodes.values()), {"A", "B", "C", "D"})
        edges = re.findall(r"(n\d+) --> (n\d+)", text)
        self.assertEqual(
            {(nodes[a], nodes[b]) for a, b in edges},
            {("A", "B"), ("A", "C"), ("B", "D"), ("C", "D")},
        )

    def test_stable_output(self):
        """Перестановка словаря и рёбер не меняет Mermaid."""
        source = {"D": (), "C": ("D",), "B": ("D",), "A": ("C", "B")}
        other = build_graph("A", source.__getitem__, 3)
        self.assertEqual(to_mermaid(self.graph, 3), to_mermaid(other, 3))

    def test_boundary(self):
        """Граница глубины получает собственный стиль и предупреждение."""
        text = to_mermaid(self.graph, 2)
        self.assertIn("class n3 boundary;", text)
        self.assertTrue(graph_metadata(self.graph, 2, text)["partial"])

    def test_cycles(self):
        """Участники цикла помечаются в Mermaid и метаданных."""
        graph = build_graph("A", {"A": ("B",), "B": ("A",)}.__getitem__, 3)
        text = to_mermaid(graph, 3)
        self.assertIn("class n0 packageRoot,cycle;", text)
        self.assertEqual(graph_metadata(graph, 3, text)["cycles"],
                         ["A → B → A"])

    def test_single_node(self):
        """Пакет без зависимостей остаётся видимым узлом."""
        graph = build_graph("A", lambda name: (), 3)
        self.assertIn('n0["A"]', to_mermaid(graph, 3))
        self.assertEqual(graph_metadata(graph, 3, "")["edges"], 0)

    def test_syntax_in_label(self):
        """Имя пакета не становится инструкцией Mermaid или HTML."""
        label = 'bad" --> injected[</script> & #]'
        escaped = mermaid_label(label)
        for unsafe in ['"', "<", ">", "[", "]", "&"]:
            self.assertNotIn(unsafe, escaped)
        self.assertIn("#34;", escaped)

    def test_write_files(self):
        """Сохраняются UTF-8 Mermaid и HTML с корректным JSON."""
        source, html = write_visualization(
            self.graph, 3, self.output / "nested",
        )
        self.assertTrue(source.is_absolute())
        self.assertTrue(html.is_file())
        content = html.read_text(encoding="utf-8")
        self.assertNotIn("{{DATA}}", content)
        payload = re.search(
            r'<script id="graph-data" type="application/json">(.*?)</script>',
            content, flags=re.DOTALL,
        ).group(1)
        self.assertEqual(json.loads(payload)["source"],
                         source.read_text(encoding="utf-8"))

    def test_script_closing_label(self):
        """Имя с </script> не закрывает JSON-блок страницы."""
        label = "</script><script>alert(1)</script>"
        graph = build_graph(label, lambda name: (), 1)
        _, html = write_visualization(graph, 1, self.output)
        content = html.read_text(encoding="utf-8")
        self.assertNotIn("</script><script>alert", content)
        self.assertIn("\\u003c/script\\u003e", content)

    def test_output_error(self):
        """Путь к обычному файлу вместо папки даёт понятную ошибку."""
        path = self.output / "file"
        path.write_text("occupied", encoding="utf-8")
        with self.assertRaises(RepositoryError):
            write_visualization(self.graph, 3, path)

    def test_browser_failure(self):
        """Ошибка запуска браузера не теряет сохранённые файлы."""
        target = "src.visualization.webbrowser.open"
        with patch(target, side_effect=OSError):
            self.assertFalse(open_visualization(self.output / "graph.html"))

    def test_cli_no_open(self):
        """Флаг --no-open сохраняет файлы без запуска браузера."""
        args = ["--visualize", "--no-open", "--output-dir", str(self.output),
                "--config", str(PROJECT / "examples/config-cycle.yaml")]
        with patch("src.main.open_visualization") as browser:
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(args), 0)
        browser.assert_not_called()
        self.assertTrue((self.output / "graph.mmd").is_file())

    def test_cli_opens_browser(self):
        """Обычный режим визуализации открывает сохранённую страницу."""
        args = ["--visualize", "--output-dir", str(self.output),
                "--config", str(PROJECT / "examples/config-test.yaml")]
        with patch("src.main.open_visualization", return_value=True) as browser:
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(args), 0)
        browser.assert_called_once_with(self.output / "graph.html")


if __name__ == "__main__":
    unittest.main()
