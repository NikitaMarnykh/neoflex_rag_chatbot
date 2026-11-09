"""Точка входа индексации."""

import sys
import logging
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
    чанки удалённых или сократившихся страниц.

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
