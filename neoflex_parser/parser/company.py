"""Парсер страницы «О компании» neoflex.ru."""

import logging
from selenium.webdriver.common.by import By
from .base import NeoflexPageParser, Strategy

logger = logging.getLogger(__name__)


class NeoflexAboutOfCompanyPageParser(NeoflexPageParser):
    """
    Парсер страницы «О компании» neoflex.ru.

    Извлекает:
      - hero-блок с заголовком «О компании» и тремя вводными абзацами;
      - блок «Миссия и принципы» — аккордеон с миссией и принципами компании.

    Стратегии поиска привязаны к семантическим якорям (текст H1/H2),
    а не к именам классов, поэтому парсер переживёт смену вёрстки.
    Аккордеон раскрывать не нужно: текст уже лежит в DOM, CSS лишь скрывает его.
    """

    # Стратегии поиска hero-блока «О компании» в порядке приоритета.
    _ABOUT_STRATEGIES: tuple[Strategy, ...] = (
        # Секция, содержащая h1 «О компании».
        (By.XPATH, "//section[.//h1[normalize-space(.)='О компании']]"),
        # Ближайшая секция-родитель h1 «О компании».
        (By.XPATH, "//h1[normalize-space(.)='О компании']/ancestor::section[1]"),
    )

    # Стратегии поиска блока «Миссия и принципы» в порядке приоритета.
    _MISSION_STRATEGIES: tuple[Strategy, ...] = (
        (By.XPATH, "//section[.//h2[normalize-space(.)='Миссия и принципы']]"),
        (By.XPATH, "//h2[normalize-space(.)='Миссия и принципы']/ancestor::section[1]"),
        (By.CSS_SELECTOR, "section.mission-principles"),
    )

    def parse(self) -> str:
        """
        Парсит страницу «О компании».

        :return: Markdown: hero-блок и блок «Миссия и принципы».
        """
        self._load_page()
        return self._join_parts([
            # Убираем <img>: фоновый Banner_about.<hash>.webp в Markdown
            # превратился бы в бесполезную ссылку ![](url).
            self._block_markdown(
                self._ABOUT_STRATEGIES, context="«О компании»", tags_to_remove=("img",),
            ),
            self._block_markdown(self._MISSION_STRATEGIES, context="«Миссия и принципы»"),
        ])
