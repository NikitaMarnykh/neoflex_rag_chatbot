"""Парсер страницы «Карьера» neoflex.ru."""

import logging
from functools import partial
from .base import NeoflexPageParser

logger = logging.getLogger(__name__)


class NeoflexAboutOfCareerPageParser(NeoflexPageParser):
    """
    Парсер страницы «Карьера» neoflex.ru.

    Извлекает смысловые блоки:
      - «Обучение и старт карьеры в Neoflex»;
      - «Жизнь в Neoflex»;
      - CTA «Мы приглашаем вас стать частью команды Neoflex!».

    Пропускает:
      - hero-блок со слоганом «Neoflex — это не просто работа…»;
      - секции «Будь профи!», «Развивайся!», «Мы поддержим!» — по контенту
        это слоганы и картинки, в RAG-выдачу они не идут.

    Устойчивость к вёрстке:
      - каждая секция ищется по точному тексту <h2>, а не по имени класса;
      - перед конвертацией из секции удаляются изображения, marquee-слайдеры
        фотографий и кнопка-ссылка «Подробнее»; остальные <a> разворачиваются
        в содержимое (URL отбрасывается, текст сохраняется, например join@neoflex.ru);
      - опустевшие после этого <div>-обёртки схлопываются итеративно.

    Заголовок страницы берётся из <title> — часть до «:» или «|», что даёт
    «Карьера в Neoflex». CTA-секция принудительно повышается до H1,
    остальные остаются H2.
    """

    # Секции к извлечению: (текст h2, желаемый уровень заголовка в Markdown).
    _TARGET_SECTIONS: tuple[tuple[str, int], ...] = (
        ("Обучение и старт карьеры в Neoflex", 2),
        ("Жизнь в Neoflex", 2),
        ("Мы приглашаем вас стать частью команды Neoflex!", 1),
    )

    # Marquee-слайдеры фотографий определяются по инлайн-стилю.
    _MARQUEE_SELECTOR = '[style*="clients-marquee"]'

    def parse(self) -> str:
        """
        Парсит страницу «Карьера».

        :return: Markdown: заголовок страницы и целевые секции.
        """
        self._load_page()

        # Заголовок берётся из <title>:
        # «Карьера в Neoflex: вакансии и развитие в ИТ | Neoflex» → «Карьера в Neoflex».
        raw_title = (self._driver.title or "").strip()
        clean_title = raw_title.split(":")[0].split("|")[0].strip()
        header = f"# {clean_title}" if clean_title else ""

        parts: list[str | None] = [header]
        parts.extend(self._parse_section(text, level) for text, level in self._TARGET_SECTIONS)
        return self._join_parts(parts)

    def _parse_section(self, text: str, level: int) -> str | None:
        """
        :param text: Точный текст h2 секции.
        :param level: Желаемый уровень заголовка секции в Markdown.
        :return: Markdown секции или None.
        """
        markdown = self._extract_section(
            partial(self._find_section_by_h2, text),
            context=text,
            remove=(self._MARQUEE_SELECTOR,),
            drop_texts=("Подробнее",),
        )
        # В исходной вёрстке заголовок секции — h2, поэтому для H1 его нужно поднять.
        if markdown and level == 1:
            markdown = markdown.replace(f"## {text}", f"# {text}", 1)
        return markdown
