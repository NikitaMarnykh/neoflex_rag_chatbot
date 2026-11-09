"""Парсер публикаций и новостей пресс-центра neoflex.ru."""

import logging
from .base import DEFAULT_STRIP_TAGS, NeoflexPageParser, Strategy
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.common.exceptions import StaleElementReferenceException, WebDriverException


logger = logging.getLogger(__name__)


class NeoflexPressArticlePageParser(NeoflexPageParser):
    """
    Парсер страницы публикации или новости пресс-центра neoflex.ru.

    Структура страницы (Next.js/Tailwind):
      - заголовок статьи — <h1> внутри <article>;
      - дата публикации — <div> сразу после <h1> (текст вида «dd месяц yyyy»);
      - основной текст статьи — .article-rich (внутри — .payload-richtext);
      - навигация «предыдущая / следующая публикация» и блок «Контакты для МЕДИА»
        вынесены за пределы .article-rich, поэтому отсекаются автоматически.

    Парсер извлекает заголовок, дату и текст статьи. Перед конвертацией
    в Markdown DOM статьи чистится: <script> удаляются, а <p> с <br><br>
    разбиваются на отдельные <p>, иначе markdownify склеит несколько абзацев
    в один.
    """

    # Порог «осмысленного» текста в контентном блоке: парсинг начинается,
    # только когда рендер отдаст больше этого значения.
    _MIN_CONTENT_LENGTH = 50

    # Контентный блок в порядке приоритета: основной, затем более узкий резервный.
    _CONTENT_STRATEGIES: tuple[Strategy, ...] = (
        (By.CSS_SELECTOR, "article .article-rich"),
        (By.CSS_SELECTOR, "article .payload-richtext"),
    )

    _TITLE_STRATEGIES: tuple[Strategy, ...] = (
        (By.XPATH, "//article//h1[normalize-space(.)!='']"),
        (By.XPATH, "//h1[normalize-space(.)!='']"),
    )

    def parse(self) -> str:
        """
        Парсит страницу: загружает её, ждёт рендер контента и собирает Markdown.

        :return: Markdown: заголовок, дата и текст статьи.
        """
        self._load_page()
        self._wait_for(self._content_ready, context="рендер контента статьи")

        return self._join_parts([
            self._block_markdown(self._TITLE_STRATEGIES, context="заголовок статьи"),
            self._parse_date(),
            self._extract_section(
                self._find_content_block,
                context="текст статьи",
                tags_to_remove=DEFAULT_STRIP_TAGS,
                remove=("script",),
                split_br=True,
                # Структуру обёрток статьи не трогаем.
                collapse_passes=0,
            ),
        ])

    def _content_ready(self, driver: WebDriver) -> bool:
        """
        Условие для WebDriverWait: контентный блок отрендерен и содержит достаточно текста.

        Проверяется именно контентный блок, а не весь <article>: внутри <article>
        лежат ещё навигация и блок «Контакты для МЕДИА», которые дали бы ложное
        срабатывание, даже если основной текст ещё не появился.

        :param driver: WebDriver, передаваемый WebDriverWait.
        :return: True, если текст блока длиннее _MIN_CONTENT_LENGTH.
        """
        try:
            return any(
                len((el.text or "").strip()) > self._MIN_CONTENT_LENGTH
                for by, value in self._CONTENT_STRATEGIES
                for el in driver.find_elements(by, value)
            )
        except StaleElementReferenceException:
            # Страница перерисовывается между опросами — это штатно, ждём дальше.
            return False

    def _find_content_block(self) -> WebElement | None:
        """
        :return: Первый найденный контентный блок или None.
        """
        return self._find_first(self._CONTENT_STRATEGIES, context="контент статьи")

    def _parse_date(self) -> str | None:
        """
        Извлекает дату публикации — <div> сразу после <h1> внутри <article>.

        Дополнительно проверяется, что в тексте есть четырёхзначный год:
        это защищает от случая, когда после смены вёрстки первым соседом <h1>
        окажется, например, подзаголовок.

        :return: Дата курсивом в Markdown или None, если дата не найдена.
        """
        try:
            for div in self._driver.find_elements(By.CSS_SELECTOR, "article h1 + div"):
                text = (div.text or "").strip()
                if self._looks_like_date(text):
                    return f"*{text}*"
        except WebDriverException as exc:
            logger.warning("Не прочитана дата статьи на %s: %s", self._url, exc.msg)
        return None

    @staticmethod
    def _looks_like_date(text: str) -> bool:
        """
        Проверяет, похож ли текст на дату: среди слов есть четырёхзначный год.

        :param text: Проверяемый текст.
        :return: True, если найден четырёхзначный числовой токен.
        """
        return any(part.isdigit() and len(part) == 4 for part in text.split())
