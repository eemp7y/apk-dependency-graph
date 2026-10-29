"""Проверки формата apk, выбора версии, загрузки и командной строки."""

from contextlib import redirect_stderr, redirect_stdout
import io
import gzip
import tarfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from src.config import Config
from src.main import main
from src.repository import (
    Package, RepositoryError, download_index, find_package, get_package,
    index_url, parse_index, unpack_index,
)


SAMPLE_INDEX = (
    "P:demo\nV:1.0-r0\nD:lib>=2 so:libc.so.1 !conflict\n\n"
    "P:demo\nV:2.0-r0\nD:other=1\n\n"
    "P:lib\nV:2.0-r0\n"
)


def make_archive(text=SAMPLE_INDEX, name="APKINDEX"):
    """Создать маленький архив в памяти для независимого от сети теста."""
    data = text.encode("utf-8")
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as archive:
        member = tarfile.TarInfo(name)
        member.size = len(data)
        archive.addfile(member, io.BytesIO(data))
    return output.getvalue()


class RepositoryTests(unittest.TestCase):
    """Загрузка и разбор индекса без реального менеджера пакетов."""

    def test_index_url(self):
        """Каталог с любым окончанием и прямой URL дают адрес индекса."""
        expected = "https://example.org/main/x86_64/APKINDEX.tar.gz"
        for url in [expected, expected.rsplit("/", 1)[0],
                    expected.rsplit("/", 1)[0] + "/"]:
            with self.subTest(url=url):
                self.assertEqual(index_url(url), expected)

    def test_url_query(self):
        """Параметры URL сохраняются, фрагмент не отправляется серверу."""
        actual = index_url("https://example.org/main/?key=1#fragment")
        self.assertEqual(
            actual, "https://example.org/main/APKINDEX.tar.gz?key=1",
        )

    def test_archive_round_trip(self):
        """Чтение настоящего tar.gz возвращает полный текст индекса."""
        self.assertEqual(unpack_index(make_archive()), SAMPLE_INDEX)

    def test_signed_archive_layout(self):
        """Перед индексом допускается отдельный gzip-поток подписи."""
        signature = tarfile.TarInfo(".SIGN.RSA.example.rsa.pub")
        data = gzip.compress(signature.tobuf()) + make_archive()
        self.assertEqual(unpack_index(data), SAMPLE_INDEX)

    def test_invalid_archive(self):
        """Вместо архива может прийти HTML или обрезанный ответ."""
        for data in [b"<html>error</html>", b"", make_archive()[:20]]:
            with self.subTest(data=data[:20]):
                with self.assertRaises(RepositoryError):
                    unpack_index(data)

    def test_missing_index(self):
        """Архив без APKINDEX вызывает понятную ошибку."""
        with self.assertRaisesRegex(RepositoryError, "отсутствует"):
            unpack_index(make_archive(name="DESCRIPTION"))

    def test_non_file_index(self):
        """APKINDEX не может быть ссылкой на другой файл."""
        output = io.BytesIO()
        with tarfile.open(fileobj=output, mode="w:gz") as archive:
            member = tarfile.TarInfo("APKINDEX")
            member.type = tarfile.SYMTYPE
            member.linkname = "other"
            archive.addfile(member)
        with self.assertRaisesRegex(RepositoryError, "обычным файлом"):
            unpack_index(output.getvalue())

    def test_exact_version_and_constraints(self):
        """Выбирается точная версия, ограничения и so: сохраняются."""
        packages = parse_index(SAMPLE_INDEX)
        package = find_package(packages, "demo", "1.0-r0")
        self.assertEqual(package.dependencies, ("lib>=2", "so:libc.so.1"))
        self.assertEqual(
            find_package(packages, "demo", "2.0-r0").dependencies,
            ("other=1",),
        )

    def test_no_dependencies_and_crlf(self):
        """Отсутствие D допустимо, поддерживаются переносы Windows."""
        packages = parse_index(SAMPLE_INDEX.replace("\n", "\r\n"))
        self.assertEqual(find_package(packages, "lib", "2.0-r0")
                         .dependencies, ())

    def test_missing_package(self):
        """Имя, которого нет в индексе, не подменяется другим пакетом."""
        with self.assertRaisesRegex(RepositoryError, "не найден"):
            find_package(parse_index(SAMPLE_INDEX), "absent", "1.0")

    def test_missing_version(self):
        """Отсутствующая версия даёт ошибку со списком доступных."""
        with self.assertRaisesRegex(RepositoryError, "1.0-r0, 2.0-r0"):
            find_package(parse_index(SAMPLE_INDEX), "demo", "999")

    def test_invalid_index(self):
        """Пустые, неполные и повреждённые записи отклоняются."""
        cases = ["", "P:demo", "V:1", "P:demo\nV:1\nbroken",
                 "P:demo\nP:other\nV:1"]
        for text in cases:
            with self.subTest(text=text):
                with self.assertRaises(RepositoryError):
                    parse_index(text)

    def test_network_errors(self):
        """Обрабатываются HTTP-ошибка, проблема соединения и тайм-аут."""
        errors = [URLError("offline"), TimeoutError("timeout"),
                  HTTPError("https://example.org", 404, "missing", {}, None)]
        for error in errors:
            with self.subTest(error=error):
                with patch("src.repository.urlopen", side_effect=error):
                    with self.assertRaisesRegex(RepositoryError, "скачать"):
                        download_index("https://example.org/main/")

    def test_full_load(self):
        """HTTP-ответ проходит распаковку, разбор и выбор версии."""
        config = Config("demo", "https://example.org/", False, "1.0-r0", 3)
        with patch("src.repository.urlopen") as opener:
            opener.return_value.__enter__.return_value.read.return_value = (
                make_archive()
            )
            self.assertEqual(get_package(config).name, "demo")
            opener.assert_called_once_with(
                "https://example.org/APKINDEX.tar.gz", timeout=30,
            )

    def test_test_mode_does_not_access_network(self):
        """Тестовый режим не обращается к URL вместо локального файла."""
        config = Config("A", "repo.yaml", True, "1.0", 3)
        with patch("src.repository.urlopen") as opener:
            with self.assertRaisesRegex(RepositoryError, "этапе 3"):
                get_package(config)
            opener.assert_not_called()

    def test_cli_dependencies(self):
        """Обычный запуск показывает имя, версию и прямые зависимости."""
        package = Package("demo", "1.0", ("lib>=2", "so:libc.so.1"))
        output = io.StringIO()
        with patch("src.main.get_package", return_value=package):
            with redirect_stdout(output):
                code = main([])
        self.assertEqual(code, 0)
        self.assertIn("Версия: 1.0", output.getvalue())
        for dependency in package.dependencies:
            self.assertIn(dependency, output.getvalue())

    def test_cli_empty_dependencies(self):
        """Пакет без зависимостей получает явное сообщение."""
        output = io.StringIO()
        with patch("src.main.get_package", return_value=Package("A", "1", ())):
            with redirect_stdout(output):
                self.assertEqual(main([]), 0)
        self.assertIn("  нет", output.getvalue())

    def test_cli_repository_failure(self):
        """Ошибка репозитория возвращает код 1 без traceback."""
        output = io.StringIO()
        with patch("src.main.get_package", side_effect=RepositoryError("404")):
            with redirect_stderr(output):
                code = main([])
        self.assertEqual(code, 1)
        self.assertIn("Ошибка репозитория: 404", output.getvalue())


if __name__ == "__main__":
    unittest.main()
