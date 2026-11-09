"""Конфигурация парсера."""

from functools import lru_cache
from lib.config import DATA_DIR, CommonSettings


class ParserSettings(CommonSettings):
    """Настройки парсера."""

    # --- Сайт ---
    base_url: str = "https://neoflex.ru/"
    robot_url: str = "https://neoflex.ru/robots.txt"
    sitemap_path: str = str(DATA_DIR / "sitemap.txt")
    # Время жизни локального кэша sitemap в секундах. По истечении sitemap
    # скачивается заново; 0 отключает кэш (всегда скачивать).
    sitemap_cache_ttl: int = 24 * 60 * 60

    # --- Сеть ---
    user_agent: str = "NeoflexRagParser/1.0"
    request_delay: float = 0.5
    timeout: int = 10
    page_load_timeout: int = 30
    max_retries: int = 3
    backoff_factor: float = 0.5
    verify_ssl: bool = True

    # --- Сохранение ---
    min_page_length: int = 200

    @property
    def headers(self) -> dict[str, str]:
        """HTTP-заголовки для запросов."""
        return {"User-Agent": self.user_agent}


@lru_cache(maxsize=1)
def get_parser_settings() -> ParserSettings:
    """Singleton ParserSettings."""
    return ParserSettings()
