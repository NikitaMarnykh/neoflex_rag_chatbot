"""Точка входа парсера Neoflex."""

import logging
import sys
import time
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import NamedTuple

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.webdriver import WebDriver as Chrome

from lib.logging_config import setup_logging
from neoflex_parser.config import ParserSettings, get_parser_settings
from neoflex_parser.fetch import build_session
from neoflex_parser.parser import NeoflexPageParser
from neoflex_parser.registry import resolve_parser_class
from neoflex_parser.robot import RobotsChecker
from neoflex_parser.sitemap import SitemapManager
from neoflex_parser.storage import PageStorage

logger = logging.getLogger(__name__)


class CrawlStats(NamedTuple):
    """Итоги обхода."""

    parsed: int
    skipped: int
    failed: int


@contextmanager
def chrome_driver(settings: ParserSettings) -> Iterator[Chrome]:
    """
    Контекстный менеджер: headless Chrome, представляющийся тем же User-Agent,
    под которым проверяется robots.txt. Гарантирует закрытие драйвера.

    :param settings: Настройки парсера.
    :return: Chrome WebDriver в headless-режиме (драйвер подбирает Selenium Manager).
    """
    options = Options()
    options.add_argument("--headless=new")
    # Нужны при запуске в контейнере: без них Chrome не стартует под root
    # и падает на маленьком /dev/shm.
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    # Без этого Chrome шлёт свой UA, и правила robots.txt, проверенные для
    # settings.user_agent, формально не относятся к клиенту, который ходит на сайт.
    options.add_argument(f"--user-agent={settings.user_agent}")
    driver = webdriver.Chrome(options=options)
    try:
        driver.set_page_load_timeout(settings.page_load_timeout)
        yield driver
    finally:
        driver.quit()
        logger.info("WebDriver закрыт")


def unique_urls(urls: Iterable[str]) -> list[str]:
    """
    Убирает повторы по имени файла, под которым страница сохранится.

    Адреса «…/about/company» и «…/about/company/» — одна страница, а в хранилище они
    дали бы один файл: без этого страница скачивалась бы дважды. Разные страницы получают
    разные имена файлов (см. PageStorage.url_to_slug), поэтому здесь не теряются.

    :param urls: URL из sitemap.
    :return: URL без повторов; порядок сохранён, из повторов остаётся первый.
    """
    unique: dict[str, str] = {}
    for url in urls:
        unique.setdefault(PageStorage.url_to_slug(url), url)
    return list(unique.values())


def parse_page(driver: Chrome, parser_class: type[NeoflexPageParser], url: str, wait_timeout: float) -> str:
    """
    Парсит одну страницу.

    Широкий перехват здесь намеренный: это верхний уровень для одной страницы,
    и сбой на ней не должен обрывать обход остального сайта.

    :param driver: WebDriver.
    :param parser_class: Класс парсера.
    :param url: URL страницы.
    :param wait_timeout: Таймаут ожидания элементов страницы в секундах.
    :return: Markdown или пустая строка при ошибке.
    """
    try:
        return parser_class(driver, url, wait_timeout).parse()
    except Exception:
        logger.exception("Не удалось распарсить %s", url)
        return ""


def crawl(
    urls: list[str],
    robots: RobotsChecker,
    storage: PageStorage,
    driver: Chrome,
    *,
    wait_timeout: float,
) -> CrawlStats:
    """
    Обходит URL и сохраняет страницы.

    Зависимости (хранилище и драйвер) передаются снаружи: владелец ресурса —
    вызывающий код, он же отвечает за закрытие драйвера. Благодаря этому
    функцию можно проверить с подставным драйвером и хранилищем.

    :param urls: Список URL из sitemap.
    :param robots: Проверка robots.txt.
    :param storage: Хранилище страниц.
    :param driver: WebDriver, через который парсятся страницы.
    :param wait_timeout: Таймаут ожидания элементов страницы в секундах.
    :return: Количество спарсенных, пропущенных и неудачных страниц.
    """
    delay = robots.get_delay()
    parsed = skipped = failed = 0

    for url in urls:
        parser_class = resolve_parser_class(url)
        if parser_class is None:
            logger.debug("Нет парсера для %s", url)
            skipped += 1
            continue
        if not robots.can_fetch(url):
            logger.info("URL %s запрещён robots.txt", url)
            skipped += 1
            continue

        logger.info("Парсинг %s", url)
        content = parse_page(driver, parser_class, url, wait_timeout)
        title = (driver.title or "").strip() or None
        if storage.save(url, content, title=title):
            parsed += 1
        else:
            failed += 1
        time.sleep(delay)

    return CrawlStats(parsed, skipped, failed)


def run_parse(settings: ParserSettings) -> int:
    """
    Основной сценарий.

    :param settings: Настройки парсера.
    :return: Код возврата (0 — успех, 1 — ничего не сохранено).
    """
    session = build_session(settings)
    try:
        robots = RobotsChecker(settings, session)
        if not robots.can_fetch(settings.site_url):
            logger.error("Доступ к %s запрещён robots.txt", settings.site_url)
            return 1

        sitemap_urls = SitemapManager(settings, robots, session).load_urls()
        urls = unique_urls(sitemap_urls)
        if not urls:
            logger.error("Нет URL для обработки")
            return 1
        logger.info("Загружено URL: %d (уникальных страниц: %d)", len(sitemap_urls), len(urls))

        storage = PageStorage(settings)
        with chrome_driver(settings) as driver:
            stats = crawl(urls, robots, storage, driver, wait_timeout=settings.element_wait_timeout)
    finally:
        session.close()

    logger.info(
        "Спарсено: %d, пропущено: %d, с ошибкой: %d",
        stats.parsed, stats.skipped, stats.failed,
    )
    return 0 if stats.parsed else 1


def main() -> int:
    """
    Верхний уровень: любая необработанная ошибка логируется со стектрейсом
    и превращается в код возврата 1.

    :return: Код возврата процесса.
    """
    settings = get_parser_settings()
    setup_logging(settings.log_level, Path(settings.log_dir) / "neoflex_parser.log")
    try:
        return run_parse(settings)
    except Exception:
        logger.exception("Фатальная ошибка парсера")
        return 1


if __name__ == "__main__":
    sys.exit(main())
