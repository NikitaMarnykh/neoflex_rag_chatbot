"""Точка входа API."""

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from langchain_openai import ChatOpenAI
from langchain_tavily import TavilySearch
from langgraph.checkpoint.memory import InMemorySaver

from lib.logging_config import setup_logging
from lib.vector_store import build_chroma_store

from app.api.error_handlers import register_error_handlers
from app.api.routes import router
from app.config import AppSettings, get_settings
from app.rag.service import RAGService
from app.rag.vector_store_reader import VectorStoreReader

logger = logging.getLogger(__name__)


def build_rag_service(settings: AppSettings) -> RAGService:
    """
    Собирает зависимости RAG-сервиса (единственное место, где они создаются).

    :param settings: Настройки API.
    :return: Готовый RAGService.
    """
    model = ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.provider_api_key,
        base_url=settings.provider_base_url,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
        max_retries=settings.llm_max_retries,
    )
    reader = VectorStoreReader(build_chroma_store(settings))

    web_search = None
    if settings.tavily_api_key is not None:
        # TavilySearch берёт ключ из переменной окружения (параметр конструктора tavily_api_key
        # в используемой версии langchain-tavily давал 401). pydantic-settings не переносит
        # значения из .env в os.environ, поэтому выставляем явно.
        os.environ["TAVILY_API_KEY"] = settings.tavily_api_key.get_secret_value()
        web_search = TavilySearch(max_results=settings.web_search_max_results)
    else:
        # Последствия для маршрутизации логирует граф; здесь — только причина.
        logger.info("TAVILY_API_KEY не задан: веб-поиск отключён")

    return RAGService(
        model,
        reader,
        web_search,
        # История хранится в памяти процесса: теряется при перезапуске и растёт с числом
        # сессий. Запускать одним воркером: у каждого воркера была бы своя история.
        # Для продакшена нужен персистентный checkpointer.
        checkpointer=InMemorySaver(),
        retrieval_top_k=settings.retrieval_top_k,
        site_url=settings.site_url,
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Создаёт RAGService при старте (загрузка модели эмбеддингов занимает время)."""
    settings = get_settings()
    app.state.rag_service = build_rag_service(settings)
    logger.info(
        "API запущено: model=%s top_k=%d web_search=%s",
        settings.llm_model,
        settings.retrieval_top_k,
        settings.tavily_api_key is not None,
    )
    yield


def create_app() -> FastAPI:
    """
    Создаёт FastAPI-приложение.

    :return: Приложение.
    """
    settings = get_settings()
    setup_logging(settings.log_level, Path(settings.log_dir) / "app.log")
    app = FastAPI(title="Neoflex RAG Chatbot", lifespan=lifespan)
    app.include_router(router)
    register_error_handlers(app)
    return app
