"""Создать три реальные диаграммы и учебные примеры для проверки браузером."""

from pathlib import Path

from src.config import load_config
from src.graph import analyze_graph
from src.repository import download_index, parse_index, unpack_index
from src.visualization import write_visualization
from tools.compare_apk import COMPARISON_DEPTH, PACKAGES, REPOSITORY, our_graph


PROJECT = Path(__file__).resolve().parent.parent
OUTPUT = PROJECT / "generated" / "demos"


def main():
    """Скачать индекс один раз, сохранить Mermaid/HTML и метаданные примеров."""
    packages = parse_index(unpack_index(download_index(REPOSITORY)))
    for name in PACKAGES:
        package, graph = our_graph(packages, name)
        paths = write_visualization(graph, COMPARISON_DEPTH, OUTPUT / name)
        print(f"{package.name}@{package.version}: {len(graph.edges)} nodes")
        print(paths[0])
    for case in ("test", "cycle", "depth", "empty", "zero"):
        path = PROJECT / "examples" / f"config-{case}.yaml"
        config = load_config(path)
        graph = analyze_graph(config, path)
        write_visualization(graph, config.max_depth, OUTPUT / case)
        print(f"Test case {case}: {len(graph.edges)} nodes")


if __name__ == "__main__":
    main()
