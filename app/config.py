"""Конфигурация API."""

from functools import lru_cache
from typing import Any

from pydantic import Field, SecretStr, field_validator

from lib.config import CommonSettings


class AppSettings(CommonSettings):
    """
    Настройки API. Пути, Chroma, эмбеддинги и логирование — в CommonSettings.

    :param provider_api_key: Ключ OpenAI-совместимого провайдера (OpenRouter).
    :param provider_base_url: Базовый URL провайдера.
    :param llm_model: Имя LLM.
    :param llm_temperature: Температура модели. RAG и веб-поиск переопределяют её на 0;
        свободный диалог и роутер используют это значение.
    :param llm_max_tokens: Максимум токенов в ответе.
    :param llm_max_retries: Число повторов при ошибке LLM.
    :param retrieval_top_k: Сколько чанков отдавать в промпт. Единственное место с этим
        значением по умолчанию: сервис и граф получают его явно.
    :param tavily_api_key: Ключ Tavily; без него (или с пустым значением) веб-поиск отключён.
    :param web_search_max_results: Сколько результатов брать из веб-поиска.
    """

    provider_api_key: SecretStr
    provider_base_url: str = "https://openrouter.ai/api/v1"

    llm_model: str = "meta-llama/llama-3.3-70b-instruct"
    llm_temperature: float = Field(default=0.2, ge=0, le=2)
    llm_max_tokens: int = Field(default=1024, gt=0)
    llm_max_retries: int = Field(default=3, ge=0)

    retrieval_top_k: int = Field(default=10, gt=0)

    tavily_api_key: SecretStr | None = None
    web_search_max_results: int = Field(default=5, gt=0)

    @field_validator("tavily_api_key", mode="before")
    @classmethod
    def _empty_key_means_disabled(cls, value: Any) -> Any:
        """
        Пустой TAVILY_API_KEY= в .env читается как пустая строка, а не как отсутствие
        значения. Без этой замены веб-поиск включился бы с пустым ключом и каждый запрос
        к нему падал бы с 401.
        """
        if isinstance(value, str) and not value.strip():
            return None
        return value


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """:return: Singleton-экземпляр AppSettings."""
    return AppSettings()
