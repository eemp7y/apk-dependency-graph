"""Получение прямых зависимостей из индекса Alpine Linux."""

from dataclasses import dataclass
import io
import tarfile
from urllib.error import URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import urlopen


INDEX_FILENAME = "APKINDEX.tar.gz"
REQUEST_TIMEOUT = 30


class RepositoryError(ValueError):
    """Ошибка загрузки индекса или поиска пакета."""


@dataclass(frozen=True)
class Package:
    """Имя, точная версия и прямые зависимости пакета."""

    name: str
    version: str
    dependencies: tuple[str, ...]
    provides: tuple[str, ...] = ()
    provider_priority: int = 0
    install_if: tuple[str, ...] = ()


def index_url(repository):
    """Получить URL индекса из адреса каталога или самого архива."""
    parts = urlsplit(repository)
    path = parts.path
    if not path.endswith("/" + INDEX_FILENAME):
        path = path.rstrip("/") + "/" + INDEX_FILENAME
    return urlunsplit(parts._replace(path=path, fragment=""))


def download_index(repository):
    """Скачать индекс стандартными средствами Python с тайм-аутом."""
    url = index_url(repository)
    try:
        with urlopen(url, timeout=REQUEST_TIMEOUT) as response:
            return response.read()
    except (URLError, OSError, ValueError) as error:
        raise RepositoryError(
            f"Не удалось скачать индекс {url}: {error}"
        ) from error


def unpack_index(data):
    """Прочитать APKINDEX из архива в памяти, не создавая файлов."""
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
            member = archive.getmember("APKINDEX")
            if not member.isfile():
                raise RepositoryError("APKINDEX должен быть обычным файлом.")
            with archive.extractfile(member) as stream:
                return stream.read().decode("utf-8")
    except (tarfile.TarError, OSError, EOFError, UnicodeError) as error:
        raise RepositoryError(
            "Повреждённый архив или текст APKINDEX."
        ) from error
    except KeyError as error:
        raise RepositoryError("В архиве отсутствует файл APKINDEX.") from error


def parse_record(record):
    """Разобрать P, V и D; записи ! обозначают конфликты."""
    fields = {}
    for line in record.splitlines():
        key, separator, value = line.partition(":")
        if not separator or len(key) != 1 or key in fields:
            raise RepositoryError("Некорректная запись в APKINDEX.")
        fields[key] = value
    if not fields.get("P") or not fields.get("V"):
        raise RepositoryError("В записи APKINDEX отсутствует имя или версия.")
    dependencies = tuple(
        item for item in fields.get("D", "").split()
        if not item.startswith("!")
    )
    try:
        priority = int(fields.get("k", "0"))
    except ValueError as error:
        raise RepositoryError("Некорректный приоритет поставщика.") from error
    return Package(
        fields["P"], fields["V"], dependencies,
        tuple(fields.get("p", "").split()), priority,
        tuple(fields.get("i", "").split()),
    )


def parse_index(text):
    """Разобрать записи пакетов, разделённые пустыми строками."""
    records = text.replace("\r\n", "\n").strip().split("\n\n")
    packages = [
        parse_record(record.strip()) for record in records if record.strip()
    ]
    if not packages:
        raise RepositoryError("Индекс APKINDEX пуст.")
    return packages


def find_package(packages, name, version):
    """Найти именно запрошенную версию, без подмены на другую."""
    available = []
    for package in packages:
        if package.name != name:
            continue
        if package.version == version:
            return package
        available.append(package.version)
    if not available:
        raise RepositoryError(f"Пакет {name} не найден в репозитории.")
    versions = ", ".join(sorted(set(available)))
    raise RepositoryError(
        f"Версия {version} пакета {name} не найдена. "
        f"Доступные версии: {versions}"
    )


def get_package(config):
    """Загрузить метаданные указанной в конфигурации версии пакета."""
    if config.test_mode:
        raise RepositoryError(
            "Для загрузки из Alpine установите test_mode: false. "
            "Для тестового графа используйте запуск без --direct."
        )
    text = unpack_index(download_index(config.repository))
    return find_package(
        parse_index(text), config.package_name, config.package_version,
    )
