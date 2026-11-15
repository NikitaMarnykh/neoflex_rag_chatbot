"""Чтение чанков из векторного хранилища с фильтром по типам документов."""

import logging

from langchain_core.documents import Document
from langchain_core.vectorstores import VectorStore

logger = logging.getLogger(__name__)

# Ключ метаданных чанка с типом документа. Должен совпадать с тем, что пишет индексатор.
DOC_TYPE_METADATA_KEY = "doc_type"


class VectorStoreReader:
    """Поиск чанков в VectorStore. Скрывает от остального кода диалект фильтров хранилища."""

    def __init__(self, vector_storage: VectorStore) -> None:
        self._vector_storage = vector_storage

    async def asimilarity_search(
        self, query: str, k: int, doc_types: list[str] | None = None
    ) -> list[Document]:
        """
        Асинхронный поиск похожих чанков.

        Синтаксис фильтра ($in) зависит от конкретного хранилища и собирается только здесь:
        при смене хранилища правится одно место.

        :param query: Поисковый запрос.
        :param k: Сколько чанков вернуть, больше нуля.
        :param doc_types: Типы документов для фильтра. None или пустой список — искать по всей базе.
        :return: Найденные чанки.
        :raise ValueError: Если k не положителен (ошибка вызывающего кода).
        """
        if k <= 0:
            raise ValueError(f"k должен быть положительным, получено {k}")

        filter_dict = {DOC_TYPE_METADATA_KEY: {"$in": doc_types}} if doc_types else None
        documents = await self._vector_storage.asimilarity_search(query, k=k, filter=filter_dict)

        # Текст запроса не логируем: он может содержать персональные данные пользователя.
        logger.debug("vector search: k=%d doc_types=%s found=%d", k, doc_types, len(documents))
        return documents
