"""Сборка LangGraph-графа диалога."""

import logging
from functools import partial

from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import Runnable
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.checkpoint.base import BaseCheckpointSaver

from app.rag.nodes import chat_node, rag_node, routing_node, select_route, web_search_node
from app.rag.state import DialogueState
from app.rag.vector_store_reader import VectorStoreReader

logger = logging.getLogger(__name__)

# Имена узлов графа. Их же использует сервис при разборе событий стриминга,
# поэтому переименование узла делается здесь и не ломает стриминг молча.
NODE_ROUTING = "routing"
NODE_RAG = "rag"
NODE_CHAT = "chat"
NODE_WEB_SEARCH = "web_search"


def _route_map(has_web_search: bool) -> dict[str, str]:
    """
    Строит карту переходов после роутера.

    Должна содержать все значения state.Route: это проверяет tests/test_graph.py.
    Без инструмента веб-поиска маршрут web_search ведёт в chat.

    :param has_web_search: Передан ли инструмент веб-поиска.
    :return: Ключи — значения route, значения — имена узлов графа.
    """
    return {
        "rag": NODE_RAG,
        "chat": NODE_CHAT,
        "web_search": NODE_WEB_SEARCH if has_web_search else NODE_CHAT,
    }


def build_graph(
    model: BaseChatModel,
    reader: VectorStoreReader,
    web_search: Runnable | None,
    *,
    checkpointer: BaseCheckpointSaver | None = None,
    retrieval_top_k: int,
    site_url: str,
) -> CompiledStateGraph:
    """
    Собирает и компилирует граф диалога.

    Регистрирует узлы маршрутизации, RAG, свободного чата и (если есть инструмент)
    веб-поиска. Зависимости узлов передаются через partial, чтобы граф не знал
    об инфраструктуре.

    :param model: LLM для всех узлов.
    :param reader: Читатель векторного хранилища для RAG.
    :param web_search: Инструмент веб-поиска или None; без него маршрут web_search ведёт в chat.
    :param checkpointer: Хранилище истории LangGraph. Если None — история не сохраняется.
    :param retrieval_top_k: Сколько чанков забирать из хранилища, больше нуля.
    :param site_url: Адрес сайта компании для ответов, когда в базе знаний нет информации.
    :return: Скомпилированный граф, готовый к вызову через ainvoke.
    :raise ValueError: Если retrieval_top_k не положителен. Проверка здесь, а не в ридере,
        чтобы приложение падало при старте, а не на каждом запросе.
    """
    if retrieval_top_k <= 0:
        raise ValueError(f"retrieval_top_k должен быть положительным, получено {retrieval_top_k}")

    graph = StateGraph(state_schema=DialogueState)

    graph.add_node(NODE_ROUTING, partial(routing_node, model))
    graph.add_node(NODE_RAG, partial(rag_node, model, reader, top_k=retrieval_top_k, site_url=site_url))
    graph.add_node(NODE_CHAT, partial(chat_node, model))
    answer_nodes = [NODE_RAG, NODE_CHAT]

    if web_search is not None:
        graph.add_node(NODE_WEB_SEARCH, partial(web_search_node, model, web_search))
        answer_nodes.append(NODE_WEB_SEARCH)
    else:
        # Роутер по-прежнему может выбрать web_search (промпт об этом не знает), и такой
        # вопрос получит ответ без актуальных данных: например, про курс валют.
        logger.warning(
            "Инструмент веб-поиска не задан: вопросы с route=web_search пойдут в chat "
            "и могут получить ответ без актуальных данных"
        )

    graph.add_edge(START, NODE_ROUTING)
    graph.add_conditional_edges(NODE_ROUTING, select_route, _route_map(web_search is not None))
    for node_name in answer_nodes:
        graph.add_edge(node_name, END)

    compiled = graph.compile(checkpointer=checkpointer)
    logger.info(
        "Граф диалога скомпилирован (checkpointer=%s, web_search=%s, retrieval_top_k=%d)",
        type(checkpointer).__name__ if checkpointer is not None else "нет",
        web_search is not None,
        retrieval_top_k,
    )
    return compiled
