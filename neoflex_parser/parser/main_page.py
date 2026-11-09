"""Парсер главной страницы neoflex.ru."""

import logging
from selenium.webdriver.common.by import By
from .base import DEFAULT_STRIP_TAGS, NeoflexPageParser, Strategy

logger = logging.getLogger(__name__)


class NeoflexMainPageParser(NeoflexPageParser):
    """Парсер главной страницы neoflex.ru."""

    # Стратегии поиска секции с карточками направлений в порядке приоритета.
    _BANNER_STRATEGIES: tuple[Strategy, ...] = (
        # Семантический якорь: заголовок первой карточки.
        (By.XPATH, "//section[contains(normalize-space(.), 'Масштабируйте использование ML')]"),
        # Ссылки на подстраницы услуг и платформ (href с завершающим слэшем).
        (By.XPATH, "//section[.//a[starts-with(@href, '/services/') or starts-with(@href, '/platforms/')]]"),
        # Структурно: первая секция после hero.
        (By.XPATH, "//section[contains(@class, 'home-greeting')]/ancestor::div[1]/following-sibling::div[1]/section"),
    )

    # Стратегии поиска заголовка «Почему Neoflex» в порядке приоритета.
    _WHY_TITLE_STRATEGIES: tuple[Strategy, ...] = (
        (By.XPATH, "//*[self::h1 or self::h2 or self::h3 or self::h4][normalize-space(.)='Почему Neoflex']"),
        (By.XPATH, "//*[contains(concat(' ', normalize-space(@class), ' '), ' why-neoflex__title ')]"),
        (By.XPATH, "//*[self::h1 or self::h2 or self::h3][contains(normalize-space(.), 'Почему Neoflex')]"),
    )

    # Стратегии поиска слайдов в порядке приоритета.
    _SLIDE_STRATEGIES: tuple[Strategy, ...] = (
        # Точный токен класса — отсекает «-wrapper», иначе в выборку попадёт и обёртка текста.
        (By.XPATH, "//div[contains(concat(' ', normalize-space(@class), ' '), ' why-neoflex__slider-item ')]"),
        # Через обёртку текста — родитель-слайд.
        (By.XPATH, "//*[contains(@class, 'why-neoflex__slider-item-wrapper')]/ancestor::div[contains(@class, 'slider-item')][1]"),
    )

    # Стратегии поиска кнопок «Узнать больше» в порядке приоритета.
    _WHY_BUTTON_STRATEGIES: tuple[Strategy, ...] = (
        (By.XPATH, "//div[contains(concat(' ', normalize-space(@class), ' '), ' why-neoflex__slider-item ')]//a[normalize-space(.)='Узнать больше']"),
        (By.XPATH, "//*[contains(concat(' ', normalize-space(@class), ' '), ' why-btn ')]"),
        (By.XPATH, "//div[contains(concat(' ', normalize-space(@class), ' '), ' why-neoflex__slider-item ')]//a[contains(concat(' ', normalize-space(@class), ' '), ' button ')]"),
    )

    def parse(self) -> str:
        """
        Парсит главную страницу.

        :return: Markdown: заголовок, баннер, блок «Почему Neoflex» со слайдами.
        """
        self._load_page()
        title = (self._driver.title or "").strip()
        header = f"# {title}" if title else ""

        parts: list[str | None] = [
            header,
            self._block_markdown(
                self._BANNER_STRATEGIES,
                context="баннер с карточками направлений",
                tags_to_remove=DEFAULT_STRIP_TAGS,
            ),
            self._block_markdown(self._WHY_TITLE_STRATEGIES, context="заголовок «Почему Neoflex»"),
        ]

        self._remove_why_buttons()
        parts.extend(self._parse_why_slides())

        return self._join_parts(parts)

    def _remove_why_buttons(self) -> None:
        """Удаляет кнопки «Узнать больше», чтобы они не попали в Markdown слайдов."""
        buttons = self._find_all_first(self._WHY_BUTTON_STRATEGIES, context="кнопки «Узнать больше»")
        for button in buttons:
            self._safe_js(
                "arguments[0].remove();", button,
                context="удаление кнопки «Узнать больше»",
            )

    def _parse_why_slides(self) -> list[str]:
        """
        Извлекает слайды блока «Почему Neoflex».

        :return: Markdown каждого слайда без дублей; пустой список, если слайды не найдены.
        """
        slides = self._find_all_first(self._SLIDE_STRATEGIES, context="слайды «Почему Neoflex»")
        if not slides:
            logger.warning("Слайды 'Почему Neoflex' не найдены на %s", self._url)
            return []

        # Дедупликация по тексту — на случай дублей слайдера.
        seen: set[str] = set()
        result: list[str] = []
        for slide in slides:
            markdown = self._element_markdown(
                slide, context="слайд «Почему Neoflex»", tags_to_remove=("img",),
            )
            if markdown and markdown not in seen:
                seen.add(markdown)
                result.append(markdown)
        return result
