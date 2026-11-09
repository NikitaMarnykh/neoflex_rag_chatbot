"""Парсер страницы проекта neoflex.ru."""

import logging
from functools import partial
from .base import NeoflexPageParser
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement

logger = logging.getLogger(__name__)

# Родитель h2 с указанным текстом — контейнер, содержащий и заголовок, и содержимое.
_FIND_H2_PARENT_JS = r"""
const h2 = Array.from(document.querySelectorAll('h2')).find(
    h => (h.textContent || '').replace(/\s+/g, ' ').trim() === arguments[0]
);
return h2 ? h2.parentElement : null;
"""


class NeoflexProjectsPageParser(NeoflexPageParser):
    """
    Парсер страницы проекта neoflex.ru (/projects/<slug>).

    Все страницы проектов построены по одному шаблону:
      - hero-блок с заголовком проекта (H1);
      - «Решение» (H2) — описание проекта и применённых технологий;
      - «Отзыв заказчика» (H2) — опционально, с ФИО, должностью и цитатой;
      - «Результаты» (H2) — итоги проекта.

    Служебные блоки («Новости и СМИ о проекте», навигация «предыдущий/следующий
    проект») не извлекаются: они не связаны с целевыми H2.

    Устойчивость к вёрстке: секции ищутся по точному тексту H2, а не по именам
    классов; для каждой берётся родитель H2. Абзацы с <br><br> разбиваются
    на отдельные <p>, ссылки разворачиваются в текст, изображения удаляются.
    """

    _TARGET_H2: tuple[str, ...] = ("Решение", "Отзыв заказчика", "Результаты")

    def parse(self) -> str:
        """
        Парсит страницу проекта.

        :return: Markdown: заголовок проекта и целевые H2-секции.
        """
        self._load_page()

        parts: list[str | None] = [
            self._block_markdown(
                ((By.XPATH, "//h1[normalize-space(.)!='']"),),
                context="заголовок проекта",
            ),
        ]
        parts.extend(
            self._extract_section(
                partial(self._find_section_block, h2_text),
                context=h2_text,
                split_br=True,
            )
            for h2_text in self._TARGET_H2
        )
        return self._join_parts(parts)

    def _find_section_block(self, h2_text: str) -> WebElement | None:
        """
        :param h2_text: Точный текст h2.
        :return: Родитель h2 или None.
        """
        return self._safe_js(_FIND_H2_PARENT_JS, h2_text, context=f"секция «{h2_text}»")
