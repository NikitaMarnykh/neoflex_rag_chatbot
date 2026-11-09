"""Логирование для neoflex_parser, indexer и app.

Консоль — читаемый текст, файл — JSON с ротацией. Время везде ISO-8601 в UTC.
Настраивается корневой логгер: так видны логи любого модуля (включая lib.*,
запуск через __main__ и сторонние библиотеки). Только stdlib, поэтому модуль
не тянет зависимостей ни в один из образов.
"""

import json
import logging
import logging.config
import logging.handlers
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CONSOLE_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
ISO_DATE_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
LOG_MAX_BYTES = 10 * 1024 * 1024
LOG_BACKUP_COUNT = 5

# Библиотеки, шумящие на INFO/DEBUG (httpx пишет строку на каждый запрос к LLM).
NOISY_LOGGERS = ("urllib3", "selenium", "httpx", "httpcore")


class UtcFormatter(logging.Formatter):
    """Текстовый форматтер со временем в UTC."""

    converter = time.gmtime


class JsonFormatter(logging.Formatter):
    """Одна запись лога — одна JSON-строка."""

    def format(self, record: logging.LogRecord) -> str:
        """
        :param record: Запись лога.
        :return: JSON-строка с временем, уровнем, логгером, сообщением и трассировкой.
        """
        entry: dict[str, Any] = {
            "time": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False)


def build_logging_config(level: str, log_path: Path) -> dict[str, Any]:
    """
    Собирает конфигурацию для dictConfig.

    :param level: Уровень логирования.
    :param log_path: Путь к файлу лога.
    :return: Словарь конфигурации.
    """
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "console": {"()": UtcFormatter, "fmt": CONSOLE_FORMAT, "datefmt": ISO_DATE_FORMAT},
            "json": {"()": JsonFormatter},
        },
        "handlers": {
            "stdout": {
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
                "formatter": "console",
            },
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "filename": str(log_path),
                "maxBytes": LOG_MAX_BYTES,
                "backupCount": LOG_BACKUP_COUNT,
                "encoding": "utf-8",
                "formatter": "json",
            },
        },
        "loggers": {name: {"level": "WARNING"} for name in NOISY_LOGGERS},
        "root": {"handlers": ["stdout", "file"], "level": level},
    }


def setup_logging(level: str, log_path: Path) -> None:
    """
    Настраивает логирование. Вызывается один раз в точке входа.

    :param level: Уровень логирования.
    :param log_path: Путь к файлу лога.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.config.dictConfig(build_logging_config(level.upper(), log_path))
