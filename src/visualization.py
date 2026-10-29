"""Текст Mermaid и просмотр графа в браузере."""

import json
from pathlib import Path
import webbrowser

from src.repository import RepositoryError


TEMPLATE = Path(__file__).parent / "templates" / "graph.html"
SAFE_CHARACTERS = " @._:+/-"


def mermaid_label(text):
    """Экранировать синтаксис диаграммы, сохранив читаемые имена пакетов."""
    return "".join(
        char if char.isalnum() or char in SAFE_CHARACTERS
        else f"#{ord(char)};" for char in text
    )


def to_mermaid(graph, max_depth):
    """Описать все узлы и рёбра Mermaid с независимыми безопасными ID."""
    names = sorted(graph.edges, key=lambda name: (graph.depths[name], name))
    identifiers = {name: f"n{index}" for index, name in enumerate(names)}
    cycle_nodes = {name for cycle in graph.cycles for name in cycle}
    lines = ["flowchart TD"]
    for name in names:
        lines.append(f'    {identifiers[name]}["{mermaid_label(name)}"]')
    for name in names:
        for child in sorted(set(graph.edges[name])):
            lines.append(f"    {identifiers[name]} --> {identifiers[child]}")
    lines.extend([
        "    classDef packageRoot fill:#1d4ed8,stroke:#1e40af,color:#fff;",
        "    classDef boundary stroke:#d97706,stroke-dasharray:5 4;",
        "    classDef cycle fill:#fff1f2,stroke:#e11d48,color:#9f1239;",
    ])
    for name in names:
        classes = []
        if graph.depths[name] == 0:
            classes.append("packageRoot")
        if graph.depths[name] >= max_depth:
            classes.append("boundary")
        if name in cycle_nodes:
            classes.append("cycle")
        if classes:
            lines.append(f"    class {identifiers[name]} {','.join(classes)};")
    return "\n".join(lines) + "\n"


def graph_metadata(graph, max_depth, source):
    """Подготовить данные страницы без подстановки имён в HTML-разметку."""
    roots = [node for node, depth in graph.depths.items() if depth == 0]
    return {
        "root": roots[0] if roots else "Граф зависимостей",
        "nodes": len(graph.edges),
        "edges": sum(len(set(children)) for children in graph.edges.values()),
        "maxDepth": max_depth,
        "partial": any(depth >= max_depth for depth in graph.depths.values()),
        "cycles": [" → ".join(cycle) for cycle in graph.cycles],
        "source": source,
    }


def write_visualization(graph, max_depth, output_dir):
    """Сохранить Mermaid и HTML; возвращать абсолютные пути файлов."""
    source = to_mermaid(graph, max_depth)
    payload = json.dumps(graph_metadata(graph, max_depth, source))
    payload = payload.replace("<", "\\u003c").replace(">", "\\u003e")
    try:
        template = TEMPLATE.read_text(encoding="utf-8")
        output_dir = Path(output_dir).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        mermaid_path = output_dir / "graph.mmd"
        html_path = output_dir / "graph.html"
        mermaid_path.write_text(source, encoding="utf-8")
        html_path.write_text(template.replace("{{DATA}}", payload),
                             encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise RepositoryError(f"Не удалось сохранить визуализацию: {error}")
    return mermaid_path, html_path


def open_visualization(path):
    """Открыть HTML в обычном браузере; при недоступности вернуть False."""
    try:
        return webbrowser.open(Path(path).resolve().as_uri(), new=2)
    except (OSError, webbrowser.Error):
        return False
