"""Загрузка URL из sitemap с локальным кэшем."""

import time
import logging
import requests
from pathlib import Path
from lxml import etree
from lxml.etree import ElementBase
from .fetch import fetch
from .robot import RobotsChecker
from .config import ParserSettings


logger = logging.getLogger(__name__)

# Не разворачиваем внешние сущности в чужом XML.
_XML_PARSER = etree.XMLParser(resolve_entities=False, no_network=True)
# Работаем по local-name, чтобы не зависеть от объявления namespace.
# url/loc — только прямые потомки, поэтому <image:loc> не попадает в выборку.
_URLSET_XPATH = "//*[local-name()='url']/*[local-name()='loc']/text()"
_INDEX_XPATH = "//*[local-name()='sitemap']/*[local-name()='loc']/text()"


class SitemapManager:
    """Загружает URL из sitemap и кэширует в файл."""

    def __init__(self, settings: ParserSettings, robots: RobotsChecker, session: requests.Session) -> None:
        self._settings = settings
        self._robots = robots
        self._session = session

    def load_urls(self) -> list[str]:
        """
        Возвращает URL из свежего кэша; если кэша нет, он пуст или старше
        sitemap_cache_ttl — скачивает sitemap заново.

        Если обновить не удалось, а устаревший кэш есть, используется он:
        лучше обойти сайт по старому списку, чем не обойти вообще.

        :return: Список URL.
        """
        cached = self._read_cache()
        if cached and self._is_cache_fresh():
            return cached

        urls = self._download_all()
        if urls:
            self._write_cache(urls)
            return urls

        if cached:
            logger.warning(
                "Не удалось обновить sitemap — используется устаревший кэш (%d URL)",
                len(cached),
            )
        return cached

    def _is_cache_fresh(self) -> bool:
        """
        :return: True, если файл кэша моложе sitemap_cache_ttl секунд.
        """
        try:
            age = time.time() - Path(self._settings.sitemap_path).stat().st_mtime
        except FileNotFoundError:
            return False
        fresh = age < self._settings.sitemap_cache_ttl
        if not fresh:
            logger.info(
                "Кэш sitemap устарел (возраст %.0f с, TTL %d с)",
                age, self._settings.sitemap_cache_ttl,
            )
        return fresh

    def _read_cache(self) -> list[str]:
        try:
            text = Path(self._settings.sitemap_path).read_text(encoding="utf-8")
        except FileNotFoundError:
            return []
        return [line.strip() for line in text.splitlines() if line.strip()]

    def _write_cache(self, urls: list[str]) -> None:
        path = Path(self._settings.sitemap_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(urls) + "\n", encoding="utf-8")
        logger.info("Sitemap сохранён в %s (%d URL)", path, len(urls))

    def _download_all(self) -> list[str]:
        """Скачивает все sitemap из robots.txt."""
        urls: list[str] = []
        for sitemap_url in self._robots.sitemaps():
            urls.extend(self._load_sitemap(sitemap_url))
        if not urls:
            logger.warning("Ни один sitemap не дал URL (проверьте robots.txt)")
        return urls

    def _load_sitemap(self, sitemap_url: str) -> list[str]:
        """
        Загружает один sitemap. Если это sitemap index — загружает вложенные.

        :param sitemap_url: URL sitemap-файла.
        :return: URL страниц; пустой список, если sitemap недоступен.
        """
        root = self._fetch_xml(sitemap_url)
        if root is None:
            return []

        if etree.QName(root).localname == "sitemapindex":
            urls: list[str] = []
            for child_url in self._extract(root, _INDEX_XPATH):
                child = self._fetch_xml(child_url)
                if child is not None:
                    urls.extend(self._extract(child, _URLSET_XPATH))
            logger.info("Sitemap index %s: %d URL", sitemap_url, len(urls))
            return urls

        urls = self._extract(root, _URLSET_XPATH)
        logger.info("Sitemap %s: %d URL", sitemap_url, len(urls))
        return urls

    def _fetch_xml(self, url: str) -> ElementBase | None:
        """
        Скачивает и парсит XML. Недоступный sitemap пропускаем и продолжаем с остальными.

        :param url: URL sitemap-файла.
        :return: Корневой элемент XML или None, если sitemap недоступен/некорректен.
        """
        if not self._robots.can_fetch(url):
            logger.warning("Sitemap %s запрещён robots.txt", url)
            return None
        try:
            text = fetch(self._session, url, timeout=self._settings.timeout)
            return etree.fromstring(text.encode("utf-8"), _XML_PARSER)
        except requests.RequestException as exc:
            logger.error("Не удалось загрузить sitemap %s: %s", url, exc)
        except etree.XMLSyntaxError as exc:
            logger.error("Некорректный XML в sitemap %s: %s", url, exc)
        return None

    @staticmethod
    def _extract(root: ElementBase, xpath: str) -> list[str]:
        return [loc.strip() for loc in root.xpath(xpath)]