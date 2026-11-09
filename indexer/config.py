"""Настройки индексации.

Специфичны для indexer'а. Общие настройки (пути, Chroma, эмбеддинги) —
в lib.config.CommonSettings.
"""

from functools import lru_cache

from lib.config import PROJECT_ROOT
from pydantic_settings import BaseSettings, SettingsConfigDict


class IndexerSettings(BaseSettings):
    """
    Настройки индексации.

    :param chunk_size: Целевой размер чанка в символах.
    :param chunk_overlap: Перекрытие между чанками.
    :param min_chunk_len: Минимальная длина чанка до склейки.
    :param min_final_len: Минимальная длина чанка после склейки.
    :param batch_size: Размер батча при записи в Chroma.
    """

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        frozen=True,
    )

    # --- Чанкинг ---
    chunk_size: int = 2000
    chunk_overlap: int = 300
    min_chunk_len: int = 150
    min_final_len: int = 50

    # --- Запись ---
    batch_size: int = 50


@lru_cache(maxsize=1)
def get_indexer_settings() -> IndexerSettings:
    """Возвращает singleton-экземпляр IndexerSettings."""
    return IndexerSettings()