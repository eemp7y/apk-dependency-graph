"""Командная строка первого этапа практической работы."""

import argparse
from dataclasses import asdict
from pathlib import Path
import sys

from src.config import ConfigError, load_config


DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "config.yaml"


def main(argv=None):
    """Вывести настройки; при ошибке вернуть код завершения 1."""
    parser = argparse.ArgumentParser(description="Анализ зависимостей apk")
    parser.add_argument(
        "--config", type=Path, default=DEFAULT_CONFIG,
        help="Путь к YAML-файлу настроек",
    )
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
    except ConfigError as error:
        print(f"Ошибка конфигурации: {error}", file=sys.stderr)
        return 1
    for key, value in asdict(config).items():
        if isinstance(value, bool):
            value = str(value).lower()
        print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
