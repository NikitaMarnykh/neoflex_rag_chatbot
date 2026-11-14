"""Создание Chroma из настроек."""

import logging

from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

from lib.config import CommonSettings

logger = logging.getLogger(__name__)

# e5 обучена с префиксами: без них заметно падает качество поиска.
PASSAGE_PREFIX = "passage: "
QUERY_PREFIX = "query: "
# Признак модели из семейства e5 в её названии. Для моделей других семейств эти префиксы
# ухудшили бы поиск, поэтому добавляются только к e5. Если подключаете модель, которой нужны
# свои префиксы или инструкция (например, к запросу), добавьте их здесь же.
E5_MODEL_MARKER = "e5"


def build_chroma_store(settings: CommonSettings) -> Chroma:
    """
    Создаёт Chroma с моделью эмбеддингов.

    Индексатор и приложение вызывают эту функцию с одними и теми же настройками:
    документы кодируются с префиксом passage, запросы с префиксом query.

    :param settings: Общие настройки.
    :return: Готовый Chroma.
    """
    use_e5_prefixes = E5_MODEL_MARKER in settings.embedding_model.lower()
    logger.info(
        "Инициализация эмбеддингов: model=%s, device=%s, e5_prefixes=%s",
        settings.embedding_model,
        settings.embedding_device,
        use_e5_prefixes,
    )

    encode_kwargs: dict = {"normalize_embeddings": True, "batch_size": settings.embedding_batch_size}
    query_encode_kwargs: dict = {"normalize_embeddings": True}
    if use_e5_prefixes:
        encode_kwargs["prompt"] = PASSAGE_PREFIX
        query_encode_kwargs["prompt"] = QUERY_PREFIX

    embeddings = HuggingFaceEmbeddings(
        model_name=settings.embedding_model,
        model_kwargs={"device": settings.embedding_device},
        encode_kwargs=encode_kwargs,
        query_encode_kwargs=query_encode_kwargs,
        show_progress=False,
    )

    logger.info("Инициализация Chroma: persist_dir=%s, collection=%s", settings.persist_dir, settings.collection_name)
    return Chroma(
        collection_name=settings.collection_name,
        embedding_function=embeddings,
        persist_directory=settings.persist_dir,
    )
