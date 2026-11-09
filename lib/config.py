"""Общие настройки: пути, Chroma, эмбеддинги, логирование.

Наследуются настройками каждого приложения (neoflex_parser, indexer, app), чтобы
знание вроде «где лежат страницы» хранилось ровно в одном месте.
Специфичные настройки — в config.py приложения.
"""

from pathlib import Path
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


# Корень проекта: пути считаются от него, а не от папки, из которой запущен процесс.
# Иначе парсер, запущенный из neoflex_parser/, положит данные в neoflex_parser/data, и индексатор их не найдёт.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"


class CommonSettings(BaseSettings):
    """
    Настройки, общие для neoflex_parser, indexer и app.

    :param pages_dir: Директория с Markdown-страницами (пишет neoflex_parser, читает indexer).
    :param persist_dir: Директория Chroma (пишет indexer, читает app).
    :param collection_name: Имя коллекции Chroma.
    :param embedding_model: Модель эмбеддингов.
    :param embedding_device: Устройство (cpu / cuda).
    :param embedding_batch_size: Размер батча при кодировании.
    :param log_level: Уровень логирования.
    :param log_dir: Директория для лог-файлов.
    """

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        frozen=True,
    )

    # --- Данные ---
    pages_dir: str = str(DATA_DIR / "pages")

    # --- Векторное хранилище ---
    persist_dir: str = str(DATA_DIR / "chroma")
    collection_name: str = "neoflex"

    # --- Эмбеддинги ---
    embedding_model: str = "intfloat/multilingual-e5-large"
    embedding_device: str = "cpu"
    embedding_batch_size: int = 32

    # --- Логирование ---
    log_level: str = "INFO"
    log_dir: str = str(PROJECT_ROOT / "logs")


@lru_cache(maxsize=1)
def get_common_settings() -> CommonSettings:
    """:return: Singleton-экземпляр CommonSettings."""
    return CommonSettings()
