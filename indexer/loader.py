"""Загрузка Markdown-файлов из директории."""

import json
import logging
from typing import Any
from pathlib import Path
from langchain_core.documents import Document


logger = logging.getLogger(__name__)


class MarkdownLoader:
    """
    Загрузчик Markdown-файлов.
    Читает все .md-файлы из указанной директории и оборачивает их в Document с метаданными
    source (URL страницы из одноимённого .json, который пишет neoflex_parser), title и document_name.

    :param base_dir: Директория с Markdown-файлами.
    """

    def __init__(self, base_dir: Path | str) -> None:
        """
        Инициализация загрузчика.

        :param base_dir: Директория с Markdown-файлами.
        """
        self._base_dir = Path(base_dir)

    def load(self) -> list[Document]:
        """
        Загружает все Markdown-файлы из директории.

        :return: Список Document-объектов.
        :raise FileNotFoundError: Если директория с Markdown-файлами не найдена.
        """
        if not self._base_dir.exists():
            raise FileNotFoundError(f"Директория с Markdown-файлами не найдена: {self._base_dir}")

        documents: list[Document] = []
        for file_path in sorted(self._base_dir.rglob("*.md")):
            text = file_path.read_text(encoding="utf-8").strip()
            if not text:
                logger.warning("Пропущен пустой файл: %s", file_path)
                continue

            meta = self._read_meta(file_path)
            documents.append(
                Document(
                    page_content=text,
                    metadata={
                        "source": meta.get("url") or str(file_path.relative_to(self._base_dir)),
                        "title": meta.get("title") or "",
                        "document_name": file_path.stem,
                    },
                )
            )

        logger.info("Загружено Markdown-файлов: %d из %s", len(documents), self._base_dir)
        return documents

    @staticmethod
    def _read_meta(md_path: Path) -> dict[str, Any]:
        """
        :param md_path: Путь к .md-файлу страницы.
        :return: Метаданные из одноимённого .json; пустой словарь, если файла нет.
        """
        try:
            return json.loads(md_path.with_suffix(".json").read_text(encoding="utf-8"))
        except FileNotFoundError:
            logger.warning("Нет метаданных для %s: source будет путём к файлу", md_path.name)
            return {}
