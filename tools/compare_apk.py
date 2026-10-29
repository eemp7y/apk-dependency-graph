"""Сравнение с реальным apk; запуск на Linux с Docker, например в CI."""

from datetime import datetime, timezone
import re
import subprocess

from src.graph import build_graph
from src.order import loading_order
from src.repository import (
    RepositoryError, download_index, parse_index, unpack_index,
)
from src.resolver import Resolver, choose_candidate, package_label


REPOSITORY = "https://dl-cdn.alpinelinux.org/alpine/v3.20/main/x86_64/"
APK_REPOSITORY = REPOSITORY.rstrip("/").rsplit("/", 1)[0]
PACKAGES = ("busybox", "zlib", "curl")
COMPARISON_DEPTH = 100
SIMULATION = r"^\(\d+/\d+\) Installing (\S+) \(([^)]+)\)"
APK_SCRIPT = r'''
root=$(mktemp -d)
apk --version
mkdir -p "$root/etc/apk" "$root/lib/apk/db" "$root/var/cache/apk"
cp -R /etc/apk/keys "$root/etc/apk/keys"
printf '%s\n' "$CHECK_REPOSITORY" > "$root/etc/apk/repositories"
: > "$root/etc/apk/world"
: > "$root/lib/apk/db/installed"
apk --root "$root" --arch x86_64 update
apk --root "$root" --arch x86_64 --no-scripts --simulate add "$CHECK_PACKAGE"
'''


def our_graph(packages, name):
    """Построить граф из уже скачанного индекса без повторного запроса."""
    root = choose_candidate([p for p in packages if p.name == name], name)
    resolver = Resolver(packages, root)
    known = {package_label(root): root}

    def dependencies(label):
        """Сопоставить исходные зависимости пакетам-поставщикам."""
        children = [
            resolver.resolve(item) for item in known[label].dependencies
        ]
        for child in children:
            known[package_label(child)] = child
        return [package_label(child) for child in children]

    graph = build_graph(package_label(root), dependencies, COMPARISON_DEPTH)
    return root, graph


def real_apk_order(package):
    """Получить план apk в пустом корне контейнера без установки пакетов."""
    command = [
        "docker", "run", "--rm", "--platform", "linux/amd64",
        "-e", f"CHECK_REPOSITORY={APK_REPOSITORY}",
        "-e", f"CHECK_PACKAGE={package.name}={package.version}",
        "alpine:3.20", "sh", "-ec", APK_SCRIPT,
    ]
    process = subprocess.run(
        command, capture_output=True, text=True, timeout=180, check=False,
    )
    raw = process.stdout + process.stderr
    if process.returncode:
        raise RuntimeError(f"apk comparison failed:\n{raw}")
    entries = re.findall(SIMULATION, process.stdout, flags=re.MULTILINE)
    if not entries:
        raise RuntimeError(f"No apk installation plan found:\n{raw}")
    return [f"{name}@{version}" for name, version in entries], raw


def explain_install_if(packages, expected, actual):
    """Объяснить только дополнения apk с выполненными условиями install_if."""
    selected = [p for p in packages if package_label(p) in set(expected)]
    if not selected:
        return {}
    resolver = Resolver(selected, selected[0])
    explained = {}
    extras = set(actual) - set(expected)
    positions = {name: index for index, name in enumerate(actual)}
    for package in packages:
        label = package_label(package)
        if label not in extras or not package.install_if:
            continue
        try:
            for condition in package.install_if + package.dependencies:
                resolver.resolve(condition)
            required = [
                package_label(resolver.resolve(item))
                for item in package.dependencies
            ]
        except RepositoryError:
            continue
        if any(positions[item] >= positions[label] for item in required):
            continue
        conditions = " ".join(package.install_if)
        explained[label] = f"install_if satisfied by our graph: {conditions}"
    return explained


def compare_order(graph, expected, actual, explained_extras=None):
    """Сравнить наборы, последовательности и зависимости до пользователей."""
    same_set = set(expected) == set(actual) and len(expected) == len(actual)
    explained_extras = explained_extras or {}
    filtered = [node for node in actual if node not in explained_extras]
    explained_set = (
        set(expected) == set(filtered) and len(expected) == len(filtered)
    )
    positions = {name: i for i, name in enumerate(actual)}
    violations = [
        f"{child} before {node}"
        for node, children in graph.edges.items() for child in children
        if node in positions and child in positions
        and positions[child] >= positions[node]
    ]
    lines = [
        f"Our order: {' -> '.join(expected)}",
        f"apk order: {' -> '.join(actual)}",
        f"Same package set: {same_set}",
        f"Same sequence: {expected == actual}",
        f"Dependency order violations in apk plan: {violations}",
    ]
    if same_set and not violations and expected != actual:
        lines.append(
            "Only independent branches differ: our tie-break is alphabetical; "
            "apk uses its transaction ordering. Both respect dependency edges."
        )
    if not same_set:
        lines.append(f"Only our graph: {sorted(set(expected) - set(actual))}")
        lines.append(f"Only apk: {sorted(set(actual) - set(expected))}")
        for package, reason in sorted(explained_extras.items()):
            lines.append(f"Explained apk addition {package}: {reason}")
        if explained_set:
            lines.append("All apk-only packages explained by install_if.")
        else:
            lines.append("Unexplained package-set difference: check solver.")
    return lines, (same_set or explained_set) and not violations


def main():
    """Проверить три пакета и напечатать воспроизводимый отчёт в лог CI."""
    packages = parse_index(unpack_index(download_index(REPOSITORY)))
    print(f"Comparison UTC: {datetime.now(timezone.utc).isoformat()}")
    print(f"Repository: {REPOSITORY}")
    print("Reference: alpine:3.20, empty root, apk add --simulate")
    all_valid = True
    for name in PACKAGES:
        package, graph = our_graph(packages, name)
        actual, raw = real_apk_order(package)
        expected = loading_order(graph)
        explained = explain_install_if(packages, expected, actual)
        lines, valid = compare_order(graph, expected, actual, explained)
        print(f"\nPackage: {package.name}={package.version}")
        print(raw)
        print("\n".join(lines))
        all_valid = all_valid and valid
    return 0 if all_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
