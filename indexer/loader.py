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
    """

    def __init__(self, base_dir: Path | str) -> None:
        """
        :param base_dir: Директория с Markdown-файлами.
        """
        self._base_dir = Path(base_dir)

    def load(self) -> list[Document]:
        """
        Загружает все Markdown-файлы из директории.

        :return: Список Document-объектов в порядке сортировки путей: так node_id чанков
            одинаковы при каждом запуске.
        :raise FileNotFoundError: Если директория с Markdown-файлами не найдена.
        :raise ValueError: Если .json с метаданными повреждён. Загрузка идёт до записи в
            хранилище, поэтому остановка не оставляет индекс в полузаписанном состоянии.
        """
        if not self._base_dir.is_dir():
            raise FileNotFoundError(f"Директория с Markdown-файлами не найдена: {self._base_dir}")

        documents: list[Document] = []
        skipped = 0
        for file_path in sorted(self._base_dir.rglob("*.md")):
            text = file_path.read_text(encoding="utf-8").strip()
            if not text:
                logger.warning("Пропущен пустой файл: %s", file_path)
                skipped += 1
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

        logger.info(
            "Загружено Markdown-файлов: %d (пропущено пустых: %d) из %s",
            len(documents),
            skipped,
            self._base_dir,
        )
        return documents

    @staticmethod
    def _read_meta(md_path: Path) -> dict[str, Any]:
        """
        :param md_path: Путь к .md-файлу страницы.
        :return: Метаданные из одноимённого .json; пустой словарь, если файла нет.
        :raise ValueError: Если файл есть, но это не корректный JSON-объект.
        """
        meta_path = md_path.with_suffix(".json")
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            logger.warning("Нет метаданных для %s: source будет путём к файлу", md_path.name)
            return {}
        except json.JSONDecodeError as exc:
            # В сообщении самого исключения нет имени файла, а их сотни.
            raise ValueError(f"Некорректный JSON метаданных: {meta_path}") from exc

        if not isinstance(meta, dict):
            raise ValueError(f"Метаданные должны быть JSON-объектом: {meta_path}")
        return meta
