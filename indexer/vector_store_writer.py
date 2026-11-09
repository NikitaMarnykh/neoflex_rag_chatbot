"""Запись документов в VectorStore батчами.

Используется только indexer'ом. Поиск — ответственность VectorStoreReader в app/rag.
"""

import logging
from langchain_core.documents import Document
from langchain_core.vectorstores import VectorStore


logger = logging.getLogger(__name__)


class VectorStoreWriter:
    """Запись документов в VectorStore."""

    def __init__(self, vector_storage: VectorStore) -> None:
        """
        :param vector_storage: Готовый VectorStore (Chroma).
        """
        self._vector_storage = vector_storage

    def add_documents(self, documents: list[Document], batch_size: int = 50) -> int:
        """
        Добавляет документы в хранилище батчами.

        :param documents: Список чанков.
        :param batch_size: Размер батча записи.
        :return: Количество добавленных документов.
        """
        if not documents:
            logger.warning("add_documents вызван с пустым списком")
            return 0

        added = 0
        for start in range(0, len(documents), batch_size):
            batch = documents[start:start + batch_size]
            self._vector_storage.add_documents(batch)
            added += len(batch)
            logger.debug("Добавлено %d/%d чанков", added, len(documents))

        logger.info("Всего добавлено: %d", added)
        return added
