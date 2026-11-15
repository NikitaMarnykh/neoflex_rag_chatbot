"""Зависимости FastAPI."""

from typing import Annotated

from fastapi import Depends, Request

from app.rag.service import RAGService


def get_rag_service(request: Request) -> RAGService:
    """
    :param request: Текущий запрос.
    :return: RAGService, созданный при старте приложения.
    """
    return request.app.state.rag_service


# Готовая аннотация для параметров эндпоинтов: Depends не повторяется в каждом из них.
RagServiceDep = Annotated[RAGService, Depends(get_rag_service)]
