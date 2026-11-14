"""Настройки индексации."""

from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from lib.config import PROJECT_ROOT


class IndexerSettings(BaseSettings):
    """
    Настройки индексации. Единственное место со значениями по умолчанию:
    чанкер и писатель получают их явно.

    :param chunk_size: Целевой размер чанка в символах.
    :param chunk_overlap: Перекрытие между чанками, меньше chunk_size.
    :param min_chunk_len: Минимальная длина чанка до склейки.
    :param min_final_len: Минимальная длина чанка после склейки.
    :param batch_size: Размер батча при записи в Chroma. У хранилища есть предел размера
        одного запроса, поэтому батч небольшой.
    """

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        frozen=True,
    )

    # --- Чанкинг ---
    chunk_size: int = Field(default=2000, gt=0)
    chunk_overlap: int = Field(default=300, ge=0)
    min_chunk_len: int = Field(default=150, ge=0)
    min_final_len: int = Field(default=50, ge=0)

    # --- Запись ---
    batch_size: int = Field(default=50, gt=0)

    @model_validator(mode="after")
    def _check_overlap_less_than_size(self) -> "IndexerSettings":
        """Перекрытие не меньше размера чанка сломало бы нарезку уже на первом документе."""
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError(
                f"chunk_overlap ({self.chunk_overlap}) должен быть меньше chunk_size ({self.chunk_size})"
            )
        return self


@lru_cache(maxsize=1)
def get_indexer_settings() -> IndexerSettings:
    """:return: Singleton-экземпляр IndexerSettings."""
    return IndexerSettings()
