"""Создание Chroma из настроек.

Функция, а не глобальная переменная: Chroma требует настроек
(persist_dir, collection, эмбеддинги), которые читаются из CommonSettings.
Создание на уровне модуля привело бы к импорту Chroma до загрузки .env.
"""

import logging
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

from lib.config import CommonSettings

logger = logging.getLogger(__name__)

# e5 обучена с префиксами: без них заметно падает качество поиска.
# При смене модели в настройках префиксы нужно пересмотреть здесь же.
PASSAGE_PREFIX = "passage: "
QUERY_PREFIX = "query: "


def build_chroma_store(settings: CommonSettings) -> Chroma:
    """
    Создаёт Chroma с моделью эмбеддингов.

    :param settings: Общие настройки.
    :return: Готовый Chroma.
    """
    logger.info("Инициализация эмбеддингов: model=%s, device=%s", settings.embedding_model, settings.embedding_device)
    embeddings = HuggingFaceEmbeddings(
        model_name=settings.embedding_model,
        model_kwargs={"device": settings.embedding_device},
        encode_kwargs={
            "normalize_embeddings": True,
            "batch_size": settings.embedding_batch_size,
            "prompt": PASSAGE_PREFIX,
        },
        query_encode_kwargs={"normalize_embeddings": True, "prompt": QUERY_PREFIX},
        show_progress=False,
    )

    logger.info("Инициализация Chroma: persist_dir=%s, collection=%s", settings.persist_dir, settings.collection_name)
    return Chroma(
        collection_name=settings.collection_name,
        embedding_function=embeddings,
        persist_directory=settings.persist_dir,
    )
