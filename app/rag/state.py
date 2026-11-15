"""Состояние графа диалога."""

from typing import Literal, TypedDict
from langgraph.graph import MessagesState

# Маршрут обработки запроса — единственное место в коде, где перечислены значения.
# Определяет, какой узел графа возьмёт управление:
# "rag" — поиск по базе знаний, "chat" — свободный диалог, "web_search" — поиск в интернете.
Route = Literal["rag", "chat", "web_search"]


class SourceDocument(TypedDict):
    """Источник ответа: URL и фрагмент текста (элемент source_documents в ответе API)."""

    source: str
    snippet: str


class DialogueState(MessagesState, total=False):
    # Поля необязательны: узлы заполняют состояние постепенно, поэтому читать их
    # нужно через .get() с запасным значением.

    # Ключ сессии: по нему checkpointer хранит историю диалога.
    session_id: str
    route: Route
    # Типы документов для фильтра поиска в базе знаний (только для route="rag").
    # Пустой список — искать по всей базе.
    doc_types: list[str]
    # Источники последнего ответа. Сбрасываются в начале каждой реплики.
    sources: list[SourceDocument]
