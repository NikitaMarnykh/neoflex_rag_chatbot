"""Точка входа индексации."""

import logging
import sys
from collections import Counter
from pathlib import Path

from indexer.chunker import DocumentChunker
from indexer.config import get_indexer_settings
from indexer.loader import MarkdownLoader
from indexer.vector_store_writer import VectorStoreWriter
from lib.config import get_common_settings
from lib.logging_config import setup_logging
from lib.vector_store import build_chroma_store

logger = logging.getLogger(__name__)


def run_index() -> int:
    """
    Полная переиндексация: загрузка страниц, чанкинг, запись в Chroma.

    Коллекция пересоздаётся, поэтому повторный запуск не плодит дубли и не оставляет
    чанки удалённых или сократившихся страниц. Всё, что может не получиться (загрузка,
    чанкинг), выполняется до очистки коллекции: при сбое там прежний индекс остаётся целым.

    :return: Код возврата (0 — успех, 1 — нечего индексировать).
    :raise FileNotFoundError: Если нет директории со страницами.
    """
    common = get_common_settings()
    indexer = get_indexer_settings()
    logger.info("Индексация запущена: pages_dir=%s", common.pages_dir)

    documents = MarkdownLoader(common.pages_dir).load()
    if not documents:
        logger.error("Не найдено ни одного .md файла в %s", common.pages_dir)
        return 1

    chunks = DocumentChunker(
        chunk_size=indexer.chunk_size,
        chunk_overlap=indexer.chunk_overlap,
        min_chunk_len=indexer.min_chunk_len,
        min_final_len=indexer.min_final_len,
    ).chunk(documents)
    if not chunks:
        # Иначе коллекция была бы очищена и пуста, а запуск выглядел бы успешным.
        logger.error("После чанкинга не осталось ни одного чанка, коллекция не тронута")
        return 1

    # Распределение по типам сразу показывает пропавший или аномально большой тип.
    by_type = Counter(chunk.metadata["doc_type"] for chunk in chunks)
    logger.info("Чанки по типам документов: %s", dict(sorted(by_type.items())))

    store = build_chroma_store(common)
    store.reset_collection()
    added = VectorStoreWriter(store).add_documents(chunks, batch_size=indexer.batch_size)
    logger.info("Индексация завершена: чанков=%d", added)
    return 0


def main() -> int:
    """
    Верхний уровень: необработанная ошибка логируется и даёт код 1.

    :return: Код возврата процесса.
    """
    common = get_common_settings()
    setup_logging(common.log_level, Path(common.log_dir) / "indexer.log")
    try:
        return run_index()
    except Exception:
        logger.exception("Фатальная ошибка индексации")
        return 1


if __name__ == "__main__":
    sys.exit(main())
