"""Сравнение компонентов версий Alpine без сторонних библиотек."""

from itertools import zip_longest
import operator
import re

from src.repository import RepositoryError


SUFFIXES = ("alpha", "beta", "pre", "rc", "", "cvs", "svn", "git", "hg", "p")
NUMBER, LETTER, SUFFIX, SUFFIX_NUMBER, COMMIT, REVISION, END = range(7)
PATTERN = re.compile(
    r"[0-9]+(?:\.[0-9]+)*[a-z]?"
    r"(?:_(?:alpha|beta|pre|rc|cvs|svn|git|hg|p)[0-9]*)*"
    r"(?:~[0-9a-f]+)?(?:-r[0-9]+)?"
)
PART_PATTERN = re.compile(
    r"(?P<number>\.?[0-9]+)|(?P<letter>[a-z])|"
    r"_(?P<suffix>alpha|beta|pre|rc|cvs|svn|git|hg|p)"
    r"(?P<suffix_number>[0-9]*)|~(?P<commit>[0-9a-f]+)|"
    r"-r(?P<revision>[0-9]+)"
)
OPERATORS = {
    "=": operator.eq, ">": operator.gt, ">=": operator.ge,
    "<": operator.lt, "<=": operator.le,
}


def version_tokens(version):
    """Разложить проверенную версию на числа, букву, суффиксы и ревизию."""
    if not PATTERN.fullmatch(version):
        raise RepositoryError(f"Неподдерживаемый формат версии: {version}")
    tokens = []
    for match in PART_PATTERN.finditer(version):
        parts = match.groupdict()
        if parts["number"] is not None:
            tokens.append((NUMBER, parts["number"].lstrip(".")))
        elif parts["suffix"] is not None:
            tokens.append((SUFFIX, SUFFIXES.index(parts["suffix"])))
            if parts["suffix_number"]:
                tokens.append((SUFFIX_NUMBER, int(parts["suffix_number"])))
        elif parts["letter"] is not None:
            tokens.append((LETTER, parts["letter"]))
        elif parts["commit"] is not None:
            tokens.append((COMMIT, parts["commit"]))
        else:
            tokens.append((REVISION, int(parts["revision"])))
    return tokens


def compare_token(left, right, initial):
    """Сравнить одинаковые компоненты, учитывая начальный ноль."""
    kind, first = left
    second = right[1]
    if kind == NUMBER:
        if initial or not (first.startswith("0") or second.startswith("0")):
            first, second = int(first), int(second)
    return (first > second) - (first < second)


def compare_versions(left, right, fuzzy=False):
    """Сравнить версии; fuzzy сравнивает префикс из целых компонентов."""
    first = version_tokens(left)
    second = version_tokens(right)
    pairs = zip_longest(first, second, fillvalue=(END, ""))
    for position, (a, b) in enumerate(pairs):
        if a[0] == b[0]:
            result = compare_token(a, b, position == 0)
            if result:
                return result
            continue
        if fuzzy and b[0] == END:
            return 0
        if a[0] == SUFFIX and a[1] < SUFFIXES.index(""):
            return -1
        if b[0] == SUFFIX and b[1] < SUFFIXES.index(""):
            return 1
        return (b[0] > a[0]) - (b[0] < a[0])
    return 0


def matches_version(actual, operation, required):
    """Проверить ограничение версии, включая ~, =~, <~ и >~."""
    if not operation:
        return True
    if actual is None:
        return False
    fuzzy = "~" in operation
    relation = compare_versions(actual, required, fuzzy=fuzzy)
    simple = operation.replace("~", "=")
    if operation in ("~", "=~", "~="):
        simple = "="
    if simple not in OPERATORS:
        raise RepositoryError(f"Неизвестное ограничение: {operation}")
    return OPERATORS[simple](relation, 0)
