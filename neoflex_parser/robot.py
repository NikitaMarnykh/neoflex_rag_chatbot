"""Работа с robots.txt."""

import logging
import requests
from .fetch import fetch
from .config import ParserSettings
from urllib.robotparser import RobotFileParser


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
        text = fetch(session, settings.robot_url, timeout=settings.timeout)
        self._parser = RobotFileParser()
        self._parser.parse(text.splitlines())
        logger.info("robots.txt загружен из %s", settings.robot_url)

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
        # Приведение к float критично: RobotFileParser может вернуть int,
        # а time.sleep() в вызывающем коде ожидает число с плавающей точкой.
        return float(raw) if raw is not None else self._default_delay

    def sitemaps(self) -> list[str]:
        """
        :return: URL sitemap-файлов, объявленных в robots.txt.
        """
        # Возврат пустого списка вместо None важен: вызывающий код ожидает итерируемый объект
        # и не должен делать проверку на None перед циклом for.
        return self._parser.site_maps() or []