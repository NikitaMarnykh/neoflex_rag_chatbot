"""
Общие настройки.
Наследуются настройками каждого приложения.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Корень проекта: пути считаются от него, а не от папки, из которой запущен процесс.
# Иначе парсер, запущенный из neoflex_parser/, положит данные в neoflex_parser/data, и индексатор их не найдёт.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"

# Допустимые уровни логирования (без NOTSET и числовых значений).
LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


class CommonSettings(BaseSettings):
    """
    Настройки, общие для neoflex_parser, indexer и app.

    :param site_url: Адрес сайта компании. Имена файлов страниц и
        типы документов в индексаторе выводятся из хоста этого адреса (HOME_DOCUMENT_NAME и
        DOC_TYPE_MAP в indexer/chunker.py): при смене сайта их нужно обновить.
    :param pages_dir: Директория с Markdown-страницами.
    :param persist_dir: Директория Chroma.
    :param collection_name: Имя коллекции Chroma.
    :param embedding_model: Модель эмбеддингов. Индексатор и приложение обязаны использовать
        одну и ту же: при смене модели коллекцию нужно переиндексировать.
    :param embedding_device: Устройство (cpu / cuda).
    :param embedding_batch_size: Размер батча при кодировании, больше нуля.
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

    # --- Сайт ---
    site_url: str = "https://neoflex.ru"

    # --- Данные ---
    pages_dir: str = str(DATA_DIR / "pages")

    # --- Векторное хранилище ---
    persist_dir: str = str(DATA_DIR / "chroma")
    collection_name: str = "neoflex"

    # --- Эмбеддинги ---
    embedding_model: str = "intfloat/multilingual-e5-large"
    embedding_device: str = "cpu"
    embedding_batch_size: int = Field(default=32, gt=0)

    # --- Логирование ---
    log_level: str = "INFO"
    log_dir: str = str(PROJECT_ROOT / "logs")

    @field_validator("site_url")
    @classmethod
    def _normalize_site_url(cls, value: str) -> str:
        """
        Убирает слэши на конце, чтобы адреса, собранные из site_url, не получили «//».
        Адрес без схемы отклоняется: парсер и бот не смогли бы построить из него ссылки.
        """
        url = value.strip().rstrip("/")
        if not url.startswith(("http://", "https://")):
            raise ValueError(f"site_url должен начинаться с http:// или https://, получено {value!r}")
        return url

    @field_validator("log_level")
    @classmethod
    def _normalize_log_level(cls, value: str) -> str:
        """
        Приводит уровень к верхнему регистру и отклоняет неизвестные значения: иначе
        опечатка в .env обнаружилась бы только внутри настройки логирования, до того как
        появился бы первый лог с объяснением.
        """
        level = value.strip().upper()
        if level not in LOG_LEVELS:
            raise ValueError(f"log_level должен быть одним из {', '.join(LOG_LEVELS)}, получено {value!r}")
        return level


@lru_cache(maxsize=1)
def get_common_settings() -> CommonSettings:
    """:return: Singleton-экземпляр CommonSettings."""
    return CommonSettings()
