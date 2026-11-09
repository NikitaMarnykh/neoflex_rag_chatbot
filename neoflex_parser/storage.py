"""Сохранение Markdown-страниц с метаданными."""

import re
import json
import logging
from typing import Any
from pathlib import Path
from urllib.parse import urlparse
from .config import ParserSettings
from datetime import datetime, timezone


logger = logging.getLogger(__name__)

# Любая последовательность символов, не являющихся строчной латинской буквой
# или цифрой, считается разделителем и заменяется на одно подчёркивание.
NON_SLUG_CHARS_PATTERN = re.compile(r"[^a-z0-9]+")


class PageStorage:
    """Сохраняет страницы и метаданные на диск."""

    def __init__(self, settings: ParserSettings) -> None:
        self._dir = Path(settings.pages_dir)
        self._min_length = settings.min_page_length
        # exist_ok=True позволяет безопасно перезапускать парсер:
        # каталог мог быть создан в предыдущем запуске.
        self._dir.mkdir(parents=True, exist_ok=True)

    def save(self, url: str, markdown: str, *, title: str | None = None) -> str | None:
        """
        Сохраняет Markdown и метаданные.

        :param url: URL страницы.
        :param markdown: Markdown-контент.
        :param title: Заголовок страницы.
        :return: Путь к .md-файлу или None, если контент пуст.
        """
        length = len((markdown or "").strip())

        if length < self._min_length:
            logger.warning(
                "Контент %s слишком короткий (%d < %d символов) — пропуск",
                url, length, self._min_length,
            )
            return None

        slug = self.url_to_slug(url)
        base = self._dir / slug
        markdown_path = base.with_suffix(".md")
        metadata_path = base.with_suffix(".json")
        markdown_path.write_text(markdown, encoding="utf-8")
        # Метаданные храним рядом с .md
        metadata: dict[str, Any] = {
            "url": url,
            "title": title,
            "parsed_at": datetime.now(timezone.utc).isoformat(),
            "length": len(markdown),
        }
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("Сохранено %s (%d символов)", markdown_path, len(markdown))
        return str(markdown_path)

    @staticmethod
    def url_to_slug(url: str) -> str:
        """
        Превращает URL в безопасное имя файла (без расширения).

        :param url: URL страницы.
        :return: Слаг из строчных латинских букв, цифр и подчёркиваний.
        """
        parsed_url = urlparse(url)
        hostname = parsed_url.netloc
        url_path = parsed_url.path.strip("/")
        slug_source = f"{hostname}/{url_path}" if url_path else hostname
        slug = NON_SLUG_CHARS_PATTERN.sub("_", slug_source.lower()).strip("_")
        return slug or "index"