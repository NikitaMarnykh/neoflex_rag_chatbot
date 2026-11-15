"""HTTP-эндпоинты."""

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.rag.service import RAGAnswer
from app.api.dependencies import RagServiceDep
from app.api.schemas import ChatRequest, ChatResponse

router = APIRouter()

# Без этих заголовков прокси могут буферизовать поток,
# и токены дойдут до клиента одним куском в конце.
SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, service: RagServiceDep) -> RAGAnswer:
    """
    Отвечает на вопрос целиком.

    :param payload: Запрос с session_id и вопросом.
    :param service: RAG-сервис.
    :return: Ответ с источниками. Ошибки обрабатывает общий обработчик приложения.
    """
    return await service.answer(payload.session_id, payload.question)


@router.post("/chat/stream")
async def chat_stream(payload: ChatRequest, service: RagServiceDep) -> StreamingResponse:
    """
    Отвечает на вопрос потоком событий (SSE).

    События: token, sources, error, done. Статус ответа всегда 200: к моменту ошибки
    заголовки уже отправлены, поэтому ошибка приходит событием error.

    :param payload: Запрос с session_id и вопросом.
    :param service: RAG-сервис.
    :return: Поток text/event-stream.
    """

    async def event_source() -> AsyncIterator[str]:
        async for event in service.stream_answer(payload.session_id, payload.question):
            # Переводы строк внутри JSON экранируются, поэтому событие не сломает формат SSE.
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_source(), media_type="text/event-stream", headers=SSE_HEADERS)


@router.get("/health")
async def health() -> dict:
    """:return: Признак того, что приложение живо."""
    return {"status": "ok"}
