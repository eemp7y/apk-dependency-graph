"""Сравнить топологию Mermaid с реальным apk dot и сохранить эталон SVG."""

import json
from pathlib import Path
import re
import subprocess

from src.repository import download_index, parse_index, unpack_index
from src.resolver import package_label
from tools.compare_apk import (
    APK_REPOSITORY, APK_SCRIPT, PACKAGES, REPOSITORY, our_graph,
)


OUTPUT = Path(__file__).resolve().parent.parent / "generated" / "demos"
DOT_MARKER = "---APK-DOT---"
DOT_SCRIPT = APK_SCRIPT + r'''
printf '\n---APK-DOT---\n'
apk --root "$root" --arch x86_64 dot "$CHECK_NAME"
'''


def real_apk_dot(package):
    """Вызвать штатный apk dot в контейнере с пустой базой пакетов."""
    command = [
        "docker", "run", "--rm", "--platform", "linux/amd64",
        "-e", f"CHECK_REPOSITORY={APK_REPOSITORY}",
        "-e", f"CHECK_PACKAGE={package.name}={package.version}",
        "-e", f"CHECK_NAME={package.name}",
        "alpine:3.20", "sh", "-ec", DOT_SCRIPT,
    ]
    process = subprocess.run(
        command, capture_output=True, text=True, timeout=180, check=False,
    )
    if process.returncode or DOT_MARKER not in process.stdout:
        raise RuntimeError(process.stdout + process.stderr)
    return process.stdout.split(DOT_MARKER, 1)[1].strip() + "\n"


def parse_dot_edges(text, packages):
    """Нормализовать подписи apk name-version в наши name@version."""
    labels = {f"{p.name}-{p.version}": package_label(p) for p in packages}
    pairs = re.findall(r'"([^"\n]+)"\s*->\s*"([^"\n]+)"', text)
    result = set()
    for parent, child in pairs:
        if parent not in labels or child not in labels:
            raise RuntimeError(f"Unknown apk dot node: {parent} -> {child}")
        result.add((labels[parent], labels[child]))
    return result


def compare_edges(graph, reference):
    """Сравнить уникальные направленные рёбра, независимо от раскладки."""
    ours = {(node, child) for node, children in graph.edges.items()
            for child in children}
    return {
        "our_nodes": len(graph.edges), "our_edges": len(ours),
        "apk_edges": len(reference), "same_edges": ours == reference,
        "only_ours": sorted(ours - reference),
        "only_apk": sorted(reference - ours),
    }


def save_reference(folder, source):
    """Сохранить исходный DOT и изображение, построенное Graphviz."""
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "reference.dot").write_text(source, encoding="utf-8")
    process = subprocess.run(
        ["dot", "-Tsvg", "-o", str(folder / "reference.svg")],
        input=source, text=True, capture_output=True, timeout=60,
        check=False,
    )
    if process.returncode:
        raise RuntimeError(f"Graphviz failed: {process.stderr}")


def main():
    """Сравнить три реальные диаграммы и сформировать машинный отчёт."""
    packages = parse_index(unpack_index(download_index(REPOSITORY)))
    results = {}
    for name in PACKAGES:
        package, graph = our_graph(packages, name)
        source = real_apk_dot(package)
        result = compare_edges(graph, parse_dot_edges(source, packages))
        result["version"] = package.version
        results[name] = result
        save_reference(OUTPUT / name, source)
        print(f"{name}: {json.dumps(result, ensure_ascii=False)}")
    (OUTPUT / "comparison.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    return 0 if all(item["same_edges"] for item in results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
