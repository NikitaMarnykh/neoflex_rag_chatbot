"""
Пакет API RAG-чат-бота для компании Neoflex.

Содержит:
    - config: настройки API (pydantic-settings);
    - main: сборка FastAPI-приложения;
    - api: HTTP-слой (схемы, роуты, зависимости);
    - rag: LangGraph-граф диалога и сервис поверх него.

Парсер сайта, индексатор и общие модули — в пакетах neoflex_parser, indexer и lib.
"""
