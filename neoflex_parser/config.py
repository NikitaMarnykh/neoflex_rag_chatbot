"""Конфигурация парсера."""

from functools import lru_cache

from pydantic import Field

from lib.config import DATA_DIR, CommonSettings


class ParserSettings(CommonSettings):
    """Настройки парсера."""

    # --- Сайт ---
    sitemap_path: str = str(DATA_DIR / "sitemap.txt")
    # Время жизни локального кэша sitemap. По истечении sitemap
    # скачивается заново; 0 отключает кэш (всегда скачивать).
    sitemap_cache_ttl: int = Field(default=24 * 60 * 60, ge=0)

    # --- Сеть ---
    user_agent: str = "NeoflexRagParser/1.0"
    # Пауза между страницами, если в robots.txt нет Crawl-delay.
    request_delay: float = Field(default=0.5, ge=0)
    # HTTP-запросы (robots.txt, sitemap).
    timeout: int = Field(default=10, gt=0)
    # Ожидание элементов страницы в браузере: отдельная настройка, потому что
    # медленный сайт и медленная сеть до sitemap настраиваются независимо.
    element_wait_timeout: int = Field(default=10, gt=0)
    page_load_timeout: int = Field(default=30, gt=0)
    max_retries: int = Field(default=3, ge=0)
    backoff_factor: float = Field(default=0.5, ge=0)
    verify_ssl: bool = True

    # --- Сохранение ---
    min_page_length: int = Field(default=200, ge=0)

    @property
    def robots_url(self) -> str:
        """Адрес robots.txt: всегда строится от site_url, отдельной настройки нет."""
        return f"{self.site_url}/robots.txt"

    @property
    def headers(self) -> dict[str, str]:
        """HTTP-заголовки для запросов."""
        return {"User-Agent": self.user_agent}


@lru_cache(maxsize=1)
def get_parser_settings() -> ParserSettings:
    """:return: Singleton-экземпляр ParserSettings."""
    return ParserSettings()
