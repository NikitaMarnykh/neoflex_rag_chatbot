"""Парсер страницы «Наши партнёры» neoflex.ru."""

import logging
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from .base import DEFAULT_STRIP_TAGS, NeoflexPageParser, Strategy

logger = logging.getLogger(__name__)

# Удаляет первый непустой h1/h2 секции и возвращает его текст.
# Удаление нужно, чтобы markdownify не выдал «## Наши партнёры»:
# заголовок подставляется отдельно как H1.
_EXTRACT_HEADING_JS = r"""
const heading = Array.from(arguments[0].querySelectorAll('h1, h2'))
    .find(h => (h.textContent || '').trim());
if (!heading) return null;
const text = heading.textContent.trim();
heading.remove();
return text;
"""


class NeoflexAboutOfPartnersPageParser(NeoflexPageParser):
    """
    Парсер страницы «Наши партнёры» neoflex.ru.

    Извлекает заголовок страницы и описания партнёров. Каждый партнёр —
    карточка <div role="button">, содержащая логотип (img с alt = название
    компании) и блок .payload-richtext с описанием.

    Логотипы и ссылки удаляются (DEFAULT_STRIP_TAGS), но название партнёра
    присутствует в тексте описания — информация не теряется.
    Заголовок извлекается отдельно и повышается до H1 («# Наши партнёры»).
    """

    # Стратегии поиска секции в порядке приоритета.
    _SECTION_STRATEGIES: tuple[Strategy, ...] = (
        # Секция, содержащая h1 или h2 «Наши партн…».
        (By.XPATH,
         "//section[.//h1[contains(normalize-space(.), 'Наши партн')]"
         " or .//h2[contains(normalize-space(.), 'Наши партн')]]"),
        # По классу — резерв на случай смены заголовка.
        (By.CSS_SELECTOR, "section.partners-block"),
    )

    # Индикатор того, что описания партнёров отрисованы (SSR обычно готов сразу).
    _CONTENT_INDICATOR = "section.partners-block .payload-richtext"

    def parse(self) -> str:
        """
        Парсит страницу «Наши партнёры».

        :return: Markdown: заголовок H1 и описания партнёров; пустая строка,
                 если секция не найдена или не прочиталась.
        """
        self._load_page()

        # Страховка от ленивой подгрузки: при SSR ожидание обходится дёшево.
        self._wait_for(
            EC.presence_of_element_located((By.CSS_SELECTOR, self._CONTENT_INDICATOR)),
            context="описания партнёров",
        )

        section = self._find_first(self._SECTION_STRATEGIES, context="секция «Наши партнёры»")
        if section is None:
            logger.warning("Секция «Наши партнёры» не найдена на %s", self._url)
            return ""

        heading = self._safe_js(
            _EXTRACT_HEADING_JS, section, context="заголовок «Наши партнёры»",
        )
        body = self._element_markdown(
            section, context="партнёры", tags_to_remove=DEFAULT_STRIP_TAGS,
        )
        if body is None:
            return ""

        header_md = f"# {heading}" if heading else None
        return self._join_parts([header_md, body])
