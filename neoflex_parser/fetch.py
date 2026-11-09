"""HTTP-запросы к robots.txt и sitemap с retry и exponential backoff."""

import logging
import requests
from .config import ParserSettings
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter


logger = logging.getLogger(__name__)


def build_session(settings: ParserSettings) -> requests.Session:
    """
    Создаёт Session с retry-политикой.

    Retry только для GET и только на 429/5xx/таймауты.
    404 не ретраится — это осмысленный ответ сервера.

    :param settings: Настройки парсера.
    :return: Настроенная сессия.
    """
    session = requests.Session()
    retry = Retry(
        total=settings.max_retries,
        backoff_factor=settings.backoff_factor,
        # 429 (rate limit) и 5xx — временные сбои сервера, их имеет смысл повторить.
        # 404/403 и прочие 4xx не ретраятся: повтор не изменит ответ.
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
        # raise_on_status=False: после исчерпания retry возвращаем последний ответ,
        # а не бросаем исключение — статус обработает вызывающий код через raise_for_status.
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update(settings.headers)
    session.verify = settings.verify_ssl
    if not settings.verify_ssl:
        # Предупреждение важно: отключение проверки SSL делает соединение уязвимым к MITM.
        logger.warning("Проверка SSL-сертификатов отключена.")
    return session


def fetch(session: requests.Session, url: str, *, timeout: float) -> str:
    """
    Загружает URL и возвращает текст ответа.

    robots.txt и sitemap по спецификациям — UTF-8, поэтому кодировка
    задаётся явно, а не угадывается requests.

    :param session: Session с retry-политикой.
    :param url: URL для загрузки.
    :param timeout: Тайм-аут запроса в секундах.
    :raises HTTPError: Если статус 4xx/5xx.
    :raises RequestException: При сетевой ошибке после всех retry.
    :return: Текст ответа.
    """
    logger.debug("GET %s", url)
    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    # Явная установка кодировки критична: requests может угадать неверно
    # (например, ISO-8859-1 по умолчанию для text/*), и XML/robots.txt
    # с кириллицей будут прочитаны как «кракозябры».
    response.encoding = "utf-8"
    return response.text