"""Проверки чтения настроек и ошибок для всех пяти параметров."""

from contextlib import redirect_stdout, redirect_stderr
from dataclasses import asdict
import io
from pathlib import Path
import tempfile
import unittest

import yaml

from src.config import ConfigError, load_config
from src.main import main


class ConfigTests(unittest.TestCase):
    """Независимые временные конфигурации для каждого сценария."""

    def setUp(self):
        """Создать временную папку и корректные настройки."""
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "config.yaml"
        self.data = {
            "package_name": "busybox",
            "repository": "https://example.org/alpine/",
            "test_mode": False,
            "package_version": "1.36.1-r29",
            "max_depth": 3,
        }

    def save(self):
        """Записать текущие настройки в UTF-8."""
        self.path.write_text(yaml.safe_dump(self.data), encoding="utf-8")

    def test_valid_config(self):
        """Корректные настройки сохраняют все значения."""
        self.save()
        self.assertEqual(asdict(load_config(self.path)), self.data)

    def test_invalid_values(self):
        """Каждый параметр отклоняет неподходящий тип или значение."""
        cases = {
            "package_name": ["", "bad name", None, 123],
            "repository": ["", "ftp://example.org", "https://", 1,
                           "https://example.org:bad", "https://a b.org"],
            "test_mode": ["false", 0, None],
            "package_version": ["", 123, None, " 1.0"],
            "max_depth": [-1, 1.5, "3", True, None],
        }
        for key, values in cases.items():
            original = self.data[key]
            for value in values:
                with self.subTest(key=key, value=value):
                    self.data[key] = value
                    self.save()
                    with self.assertRaisesRegex(ConfigError, key):
                        load_config(self.path)
            self.data[key] = original

    def test_missing_keys(self):
        """Отсутствие любого обязательного ключа вызывает ошибку."""
        for key in list(self.data):
            value = self.data.pop(key)
            self.save()
            with self.subTest(key=key):
                with self.assertRaisesRegex(ConfigError, key):
                    load_config(self.path)
            self.data[key] = value

    def test_extra_key(self):
        """Опечатки в названиях настроек не игнорируются."""
        self.data["unknown"] = 1
        self.save()
        with self.assertRaisesRegex(ConfigError, "Неизвестные"):
            load_config(self.path)

    def test_test_repository(self):
        """Относительный путь считается от папки конфигурации."""
        self.data.update(test_mode=True, repository="repo.yaml")
        self.save()
        with self.assertRaisesRegex(ConfigError, "repository"):
            load_config(self.path)
        self.path.with_name("repo.yaml").write_text("A: []", encoding="utf-8")
        self.assertTrue(load_config(self.path).test_mode)

    def test_invalid_documents(self):
        """Пустой файл, список и сломанный YAML отклоняются."""
        for text in ["", "- package", "package_name: ["]:
            with self.subTest(text=text):
                self.path.write_text(text, encoding="utf-8")
                with self.assertRaises(ConfigError):
                    load_config(self.path)

    def test_missing_file(self):
        """Отсутствие файла превращается в понятную ошибку."""
        with self.assertRaises(ConfigError):
            load_config(self.path)

    def test_cli_success(self):
        """CLI выводит все параметры в формате ключ-значение."""
        self.save()
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(["--config", str(self.path)])
        self.assertEqual(code, 0)
        for key, value in self.data.items():
            expected = str(value).lower() if type(value) is bool else value
            self.assertIn(f"{key}: {expected}", output.getvalue())

    def test_cli_failure(self):
        """CLI сообщает об ошибке и возвращает ненулевой код."""
        output = io.StringIO()
        with redirect_stderr(output):
            code = main(["--config", str(self.path)])
        self.assertEqual(code, 1)
        self.assertIn("Ошибка конфигурации", output.getvalue())


if __name__ == "__main__":
    unittest.main()
