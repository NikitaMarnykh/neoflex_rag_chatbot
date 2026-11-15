"""Общий обработчик необработанных исключений."""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

GENERIC_ERROR_MESSAGE = "Внутренняя ошибка сервера"


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Логирует необработанное исключение и отвечает клиенту статусом 500 без деталей.

    В лог идут трассировка, метод и путь; тело запроса и query не пишем: они могут
    содержать данные пользователя.

    :param request: Запрос, при обработке которого возникло исключение.
    :param exc: Исключение.
    :return: Ответ 500 с нейтральным сообщением.
    """
    logger.error("Необработанное исключение: %s %s", request.method, request.url.path, exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": GENERIC_ERROR_MESSAGE})


def register_error_handlers(app: FastAPI) -> None:
    """
    Подключает общий обработчик: сюда попадают все ошибки, которые эндпоинты не перехватили
    (сбои модели, хранилища, веб-поиска). Ошибки стриминга сюда не доходят: после отправки
    заголовков их сообщает сервис событием error.

    :param app: Приложение.
    """
    app.add_exception_handler(Exception, unhandled_exception_handler)
