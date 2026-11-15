"""Сервис диалога: запускает граф и отдаёт ответ целиком или потоком событий."""

import logging
import time
from collections.abc import AsyncIterator
from typing import Any, TypedDict

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langchain_core.runnables import Runnable
from langgraph.checkpoint.base import BaseCheckpointSaver

from app.rag.dialogue_graph import (
    NODE_CHAT,
    NODE_RAG,
    NODE_WEB_SEARCH,
    build_graph,
)
from app.rag.state import SourceDocument
from app.rag.vector_store_reader import VectorStoreReader

logger = logging.getLogger(__name__)

# Узлы, после которых отдаём источники.
SOURCE_NODES = (NODE_RAG, NODE_WEB_SEARCH)
# Узлы, токены которых уходят пользователю. Узла маршрутизации здесь нет намеренно:
# он тоже вызывает модель (structured output), и без этого фильтра в поток попал бы
# JSON классификатора.
TOKEN_NODES = (NODE_RAG, NODE_CHAT, NODE_WEB_SEARCH)


class RAGAnswer(TypedDict):
    """Полный ответ сервиса (формат ответа API)."""

    answer: str
    source_documents: list[SourceDocument]
    session_id: str


def _chunk_text(chunk: Any) -> str:
    """
    Достаёт текст из чанка стриминга.

    Провайдеры и версии langchain-core отдают его по-разному: `.text` бывает
    свойством или методом, а `.content` — строкой или списком блоков.

    :param chunk: Чанк модели из события on_chat_model_stream.
    :return: Текст токена или пустая строка, если текста нет.
    """
    text = getattr(chunk, "text", "")
    if callable(text):
        text = text()
    if isinstance(text, str) and text:
        return text

    content = getattr(chunk, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block if isinstance(block, str) else block.get("text", "")
            for block in content
            if isinstance(block, (str, dict))
        )
    return ""


class RAGService:
    """Запускает граф диалога (RAG, свободный чат, веб-поиск) для одной реплики."""

    def __init__(
        self,
        model: BaseChatModel,
        reader: VectorStoreReader,
        web_search: Runnable | None = None,
        *,
        checkpointer: BaseCheckpointSaver | None = None,
        retrieval_top_k: int,
        site_url: str,
    ) -> None:
        """
        :param model: LLM для всех узлов графа.
        :param reader: Читатель векторного хранилища для RAG.
        :param web_search: Инструмент веб-поиска, например TavilySearch; None — без веб-поиска.
        :param checkpointer: Хранилище истории диалога; None — история не сохраняется.
        :param retrieval_top_k: Сколько чанков забирать из хранилища.
        :param site_url: Адрес сайта компании (из настроек) для ответов без данных в базе.
        :raise ValueError: Если retrieval_top_k не положителен.
        """
        self._graph = build_graph(
            model=model,
            reader=reader,
            web_search=web_search,
            checkpointer=checkpointer,
            retrieval_top_k=retrieval_top_k,
            site_url=site_url,
        )

    @staticmethod
    def _prepare_run(session_id: str, question: str) -> tuple[dict, dict]:
        """
        :param session_id: Идентификатор сессии (используется как thread_id).
        :param question: Вопрос пользователя.
        :return: Начальное состояние графа и config запуска. Историю добавляет checkpointer.
        """
        initial_state = {"session_id": session_id, "messages": [HumanMessage(content=question)]}
        config = {"configurable": {"thread_id": session_id}}
        return initial_state, config

    async def answer(self, session_id: str, question: str) -> RAGAnswer:
        """
        Формирует полный ответ на вопрос.

        :param session_id: Идентификатор сессии (используется как thread_id).
        :param question: Вопрос пользователя.
        :return: Словарь {answer, source_documents, session_id}.
        :raise Exception: Исключения графа пробрасываются наверх
            и обрабатываются на верхнем уровне приложения.
        """
        started_at = time.perf_counter()
        initial_state, config = self._prepare_run(session_id, question)
        final_state = await self._graph.ainvoke(initial_state, config=config)

        sources = final_state.get("sources") or []
        logger.info(
            "session_id=%s mode=answer status=ok duration_ms=%d sources=%d route=%s",
            session_id,
            int((time.perf_counter() - started_at) * 1000),
            len(sources),
            final_state.get("route"),
        )
        return {
            "answer": final_state["messages"][-1].content,
            "source_documents": sources,
            "session_id": session_id,
        }

    async def stream_answer(self, session_id: str, question: str) -> AsyncIterator[dict]:
        """
        Формирует ответ в режиме стриминга.

        Отдаёт события по мере поступления: токены ответа, затем источники (когда узел
        rag или web_search завершился) и в конце "done". При ошибке отдаёт событие
        "error" и всё равно завершает поток событием "done".

        :param session_id: Идентификатор сессии (используется как thread_id).
        :param question: Вопрос пользователя.
        :return: Асинхронный итератор событий {"type", "data"}.
        """
        started_at = time.perf_counter()
        initial_state, config = self._prepare_run(session_id, question)

        # "cancelled" остаётся, если клиент оборвал соединение: исключение при этом
        # не перехватывается, и в finally видно, что поток не дошёл до конца.
        status = "cancelled"
        sources_count = 0
        sources_sent = False

        try:
            async for event in self._graph.astream_events(initial_state, config=config, version="v2"):
                kind = event["event"]
                node_name = event.get("metadata", {}).get("langgraph_node")

                if kind == "on_chain_end" and node_name in SOURCE_NODES and not sources_sent:
                    # Метаданные узла наследуют и вложенные запуски, поэтому проверяем,
                    # что вернулся результат узла (dict с sources), и отдаём источники
                    # один раз за запрос.
                    output = event["data"].get("output")
                    if isinstance(output, dict) and output.get("sources"):
                        sources_sent = True
                        sources_count = len(output["sources"])
                        yield {"type": "sources", "data": output["sources"]}

                elif kind == "on_chat_model_stream" and node_name in TOKEN_NODES:
                    token = _chunk_text(event["data"]["chunk"])
                    if token:
                        yield {"type": "token", "data": token}
            status = "ok"

        except Exception:
            # Заголовки ответа уже отправлены: HTTP-ошибку вернуть нельзя, сообщаем событием.
            status = "error"
            logger.exception("session_id=%s ошибка стриминга", session_id)
            yield {"type": "error", "data": "Не удалось сформировать ответ"}
        finally:
            logger.info(
                "session_id=%s mode=stream status=%s duration_ms=%d sources=%d",
                session_id,
                status,
                int((time.perf_counter() - started_at) * 1000),
                sources_count,
            )

        yield {"type": "done", "data": None}
