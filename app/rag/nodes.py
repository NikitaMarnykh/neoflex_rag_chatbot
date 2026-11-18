"""Узлы графа диалога."""

import logging
from typing import Literal

from langchain_core.documents import Document
from langchain_core.exceptions import OutputParserException
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.runnables import Runnable
from pydantic import BaseModel, Field, ValidationError

from app.rag.prompts import chat_prompt, rag_prompt, router_prompt, web_prompt
from app.rag.state import DialogueState, Route, SourceDocument
from app.rag.vector_store_reader import VectorStoreReader

logger = logging.getLogger(__name__)

# Лимит символов для сниппета источника. Ограничивает размер ответа API.
SNIPPET_MAX_LEN = 200
# При сомнении выбираем rag (то же правило записано в ROUTER_SYSTEM).
DEFAULT_ROUTE: Route = "rag"
# 20 сообщений (≈10 пар «вопрос-ответ»). Ограничивает размер промпта в длинных сессиях.
HISTORY_MESSAGES_LIMIT = 20
# Больше типов в фильтре — значит вопрос общий; правило есть и в ROUTER_SYSTEM.
DOC_TYPES_MAX = 3
# Сообщение об ошибке инструмента в лог обрезаем: оно приходит извне и может быть длинным.
ERROR_LOG_MAX_LEN = 200

# Контекст для веб-промпта, когда результатов нет: модель должна понимать, что поиск
# ничего не дал или сломался, а не додумывать ответ. Тексты согласованы с WEB_SYSTEM.
NO_RESULTS_CONTEXT = "Нет результатов поиска."
SEARCH_FAILED_CONTEXT = "Поиск временно недоступен."

# Типы документов из метаданных чанков. Должен совпадать с DOC_TYPE_DESCRIPTIONS
# в prompts.py: расхождение ловит tests/test_prompts.py.
DocType = Literal[
    "company_info", "clients_partners", "contacts_career", "platform",
    "service", "industry", "project", "publication", "news",
]


class RouteDecision(BaseModel):
    """Схема ответа роутера — гарантирует валидное значение route и doc_types."""

    route: Route = Field(description="Категория вопроса: rag, chat или web_search")
    doc_types: list[DocType] | None = Field(
        default=None,
        max_length=DOC_TYPES_MAX,
        description=(
            "Типы документов базы знаний для поиска. Только для route=rag; "
            "пустой список или None — искать по всей базе."
        ),
    )


def _split_dialogue(state: DialogueState) -> tuple[str, list[BaseMessage]]:
    """
    Делит состояние на последний вопрос и историю.

    :param state: Состояние графа.
    :return: Последний вопрос пользователя и предыдущие сообщения (не больше лимита).
    :raise ValueError: Если в состоянии нет сообщений.
    """
    messages = state["messages"]
    if not messages:
        raise ValueError("В состоянии нет сообщений: нечего отвечать")
    *history, last = messages
    return last.content, history[-HISTORY_MESSAGES_LIMIT:]


def _format_chunk(doc: Document) -> str:
    """
    Форматирует чанк для контекста промпта.

    :param doc: Найденный чанк.
    :return: Текст чанка со строкой «[источник | раздел]», чтобы модель не путала страницы.
    """
    meta = doc.metadata
    where = " / ".join(filter(None, (meta.get("title"), meta.get("section"), meta.get("subsection"))))
    return f"[{meta.get('source', '')} | {where}]\n{doc.page_content}"


def _make_source(url: str, text: str) -> SourceDocument:
    """
    :param url: Адрес источника.
    :param text: Полный текст фрагмента.
    :return: Источник для ответа API с обрезанным сниппетом.
    """
    return {"source": url, "snippet": text[:SNIPPET_MAX_LEN].strip()}


def _sources_from_documents(documents: list[Document]) -> list[SourceDocument]:
    """
    :param documents: Найденные чанки.
    :return: Источники без повторов по URL (берётся первый, самый релевантный чанк страницы).
    """
    sources: list[SourceDocument] = []
    seen: set[str] = set()
    for doc in documents:
        url = doc.metadata.get("source", "")
        if url not in seen:
            seen.add(url)
            sources.append(_make_source(url, doc.page_content))
    return sources


def _parse_search_results(raw: object, session_id: str | None) -> tuple[list[dict], bool]:
    """
    Достаёт результаты из ответа инструмента веб-поиска.

    Инструмент (Tavily) при сбое — неверный ключ, лимит, сеть — возвращает {"error": ...},
    а не бросает исключение, поэтому ошибку приходится разбирать вручную.

    :param raw: Сырой ответ инструмента.
    :param session_id: Идентификатор сессии для логов.
    :return: Список результатов и признак сбоя поиска (чтобы отличить его от пустой выдачи).
    """
    if not isinstance(raw, dict):
        logger.warning(
            "session_id=%s web_search: неожиданный тип ответа инструмента: %s",
            session_id,
            type(raw).__name__,
        )
        return [], True

    if raw.get("error"):
        logger.error(
            "session_id=%s web_search: ошибка инструмента: %.*s",
            session_id,
            ERROR_LOG_MAX_LEN,
            raw["error"],
        )
        return [], True

    return [item for item in raw.get("results", []) if isinstance(item, dict)], False


async def routing_node(model: BaseChatModel, state: DialogueState) -> dict:
    """
    Классифицирует последний вопрос пользователя и определяет маршрут графа.

    При невалидном ответе модели откатывается на DEFAULT_ROUTE. Заодно сбрасывает
    источники и типы документов: checkpointer хранит состояние между репликами, и без
    сброса chat-ответ вернул бы источники предыдущего rag-ответа, а rag — старый фильтр.

    :param model: Языковая модель для классификации.
    :param state: Текущее состояние графа с историей сообщений.
    :return: Словарь {"route": ..., "doc_types": [...], "sources": []}.
    :raise Exception: Сетевые ошибки и ошибки провайдера пробрасываются наверх
        и обрабатываются на верхнем уровне приложения.
    """
    session_id = state.get("session_id")
    question, history = _split_dialogue(state)
    router = router_prompt | model.with_structured_output(RouteDecision)

    try:
        raw = await router.ainvoke({"history": history, "question": question})
        decision = raw if isinstance(raw, RouteDecision) else RouteDecision.model_validate(raw)
    except (OutputParserException, ValidationError):
        logger.warning(
            "session_id=%s router вернул невалидный ответ, fallback=%s",
            session_id,
            DEFAULT_ROUTE,
            exc_info=True,
        )
        decision = RouteDecision(route=DEFAULT_ROUTE)

    doc_types = decision.doc_types if decision.route == "rag" else None
    logger.info(
        "session_id=%s router=%s doc_types=%s",
        session_id,
        decision.route,
        doc_types,
    )
    return {"route": decision.route, "doc_types": doc_types or [], "sources": []}


def select_route(state: DialogueState) -> Route:
    """
    Выбирает ребро графа после роутера.

    :param state: Текущее состояние графа.
    :return: Значение route — ключ в карте переходов графа.
    """
    return state.get("route", DEFAULT_ROUTE)


async def rag_node(
    model: BaseChatModel,
    reader: VectorStoreReader,
    state: DialogueState,
    *,
    top_k: int,
    site_url: str,
) -> dict:
    """
    Отвечает на вопрос по базе знаний компании.

    Ищет похожие чанки (с фильтром по типам документов, если роутер их выбрал),
    формирует контекст и сниппеты источников, затем генерирует ответ через
    RAG-промпт с temperature=0.

    :param model: Языковая модель для генерации ответа.
    :param reader: Читатель векторного хранилища.
    :param state: Текущее состояние графа с историей сообщений.
    :param top_k: Количество чанков для извлечения.
    :param site_url: Адрес сайта компании: на него промпт отсылает, если в базе нет ответа.
    :return: Словарь с ответом модели и списком источников.
    :raise Exception: Ошибки хранилища и модели пробрасываются наверх
        и обрабатываются на верхнем уровне приложения.
    """
    session_id = state.get("session_id")
    question, history = _split_dialogue(state)
    doc_types = state.get("doc_types") or []

    documents = await reader.asimilarity_search(question, k=top_k, doc_types=doc_types)
    if doc_types and not documents:
        # Страховка: роутер мог выбрать не тот тип, тогда ищем по всей базе.
        logger.warning(
            "session_id=%s фильтр %s ничего не нашёл, повтор без фильтра", session_id, doc_types
        )
        documents = await reader.asimilarity_search(question, k=top_k)
    if not documents:
        # Пустой контекст даже без фильтра — признак проблемы с индексом, а не с вопросом.
        logger.warning("session_id=%s rag: контекст пуст даже без фильтра, проверьте индекс", session_id)

    context = "\n\n".join(_format_chunk(doc) for doc in documents)
    sources = _sources_from_documents(documents)

    chain = rag_prompt | model.bind(temperature=0)
    response: AIMessage = await chain.ainvoke(
        {"context": context, "history": history, "question": question, "site": site_url}
    )

    logger.info("session_id=%s rag: docs=%d filter=%s", session_id, len(documents), doc_types)
    return {"messages": [response], "sources": sources}


async def chat_node(model: BaseChatModel, state: DialogueState) -> dict:
    """
    Отвечает на вопрос в режиме свободного диалога.

    :param model: Языковая модель для генерации ответа.
    :param state: Текущее состояние графа с историей сообщений.
    :return: Словарь с ответом модели в ключе "messages".
    """
    question, history = _split_dialogue(state)

    chain = chat_prompt | model
    response: AIMessage = await chain.ainvoke({"history": history, "question": question})

    logger.info("session_id=%s chat: ответ сформирован", state.get("session_id"))
    return {"messages": [response]}


async def web_search_node(model: BaseChatModel, web_search: Runnable, state: DialogueState) -> dict:
    """
    Отвечает на вопрос с использованием результатов веб-поиска.

    :param model: Языковая модель для генерации ответа.
    :param web_search: Инструмент веб-поиска с методом ainvoke.
    :param state: Текущее состояние графа с историей сообщений.
    :return: Словарь с ответом модели и списком источников.
    :raise Exception: Сетевые ошибки и ошибки модели пробрасываются наверх
        и обрабатываются на верхнем уровне приложения.
    """
    session_id = state.get("session_id")
    question, history = _split_dialogue(state)

    raw = await web_search.ainvoke({"query": question})
    results, search_failed = _parse_search_results(raw, session_id)

    context_parts = [f"[{item.get('title', '')}]({item.get('url', '')})\n{item.get('content', '')}" for item in results]
    sources = [_make_source(item.get("url", ""), item.get("content", "")) for item in results]

    if context_parts:
        context = "\n\n".join(context_parts)
    else:
        context = SEARCH_FAILED_CONTEXT if search_failed else NO_RESULTS_CONTEXT

    chain = web_prompt | model.bind(temperature=0)
    response: AIMessage = await chain.ainvoke({"context": context, "history": history, "question": question})

    logger.info("session_id=%s web_search: results=%d failed=%s", session_id, len(results), search_failed)
    return {"messages": [response], "sources": sources}
