"""Работа с robots.txt."""

import logging
from urllib.robotparser import RobotFileParser

import requests

from .config import ParserSettings
from .fetch import fetch

logger = logging.getLogger(__name__)


class RobotsChecker:
    """Проверяет доступность URL по robots.txt."""

    def __init__(self, settings: ParserSettings, session: requests.Session) -> None:
        """
        :param settings: Настройки парсера.
        :param session: Session с retry.
        :raises RequestException: Если robots.txt не загрузился.
        """
        self._user_agent = settings.user_agent
        self._default_delay = settings.request_delay
        # Исключение пробрасывается наверх намеренно: если robots.txt недоступен,
        # парсер не должен работать вслепую, игнорируя правила сайта.
        text = fetch(session, settings.robots_url, timeout=settings.timeout)
        self._parser = RobotFileParser()
        self._parser.parse(text.splitlines())
        logger.info("robots.txt загружен из %s", settings.robots_url)

    def can_fetch(self, url: str) -> bool:
        """
        :param url: URL для проверки.
        :return: True, если URL разрешён для нашего User-Agent.
        """
        result = self._parser.can_fetch(self._user_agent, url)
        logger.debug("can_fetch(%s) = %s", url, result)
        return result

    def get_delay(self) -> float:
        """
        :return: crawl-delay из robots.txt или базовая задержка.
        """
        raw = self._parser.crawl_delay(self._user_agent)
        # RobotFileParser возвращает crawl-delay числом из файла (int или str-подобным
        # значением), а контракт метода — float.
        return float(raw) if raw is not None else self._default_delay

    def sitemaps(self) -> list[str]:
        """
        :return: URL sitemap-файлов, объявленных в robots.txt.
        """
        # Пустой список вместо None: вызывающему коду не нужна проверка перед циклом for.
        return self._parser.site_maps() or []
