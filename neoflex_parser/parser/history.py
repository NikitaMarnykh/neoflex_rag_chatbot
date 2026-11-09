"""Парсер страницы «История компании» neoflex.ru."""

import logging
from .base import DEFAULT_STRIP_TAGS, NeoflexPageParser, Strategy
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.common.exceptions import StaleElementReferenceException


logger = logging.getLogger(__name__)

# Тексты кнопок карусели. textContent, а не element.text: карусель сдвинута
# через transform, большинство кнопок за пределами overflow-x-clip,
# и Selenium возвращает для них пустую строку.
_BUTTON_TEXTS_JS = r"""
return Array.from(arguments[0].querySelectorAll('button'))
    .map(b => (b.textContent || '').trim());
"""

# Кнопки года внутри карусели (по первому слову textContent).
_FIND_YEAR_BUTTONS_JS = r"""
const target = arguments[1];
return Array.from(arguments[0].querySelectorAll('button'))
    .filter(b => (b.textContent || '').trim().split(/\s+/)[0] === target);
"""

# Клик из JS не проверяет видимость по координатам, поэтому работает для
# кнопок, обрезанных каруселью; scrollIntoView подводит кнопку в clip-контейнер.
_CLICK_JS = r"""
const el = arguments[0];
try { el.scrollIntoView({block: 'center', inline: 'center'}); } catch (e) {}
el.click();
return true;
"""

# Контейнер деталей года: от видимого заголовка с текстом года поднимаемся
# не выше 5 уровней до родителя, содержащего .company-history-rich. Такая
# навигация переживёт добавление и переименование промежуточных обёрток.
_FIND_DETAIL_JS = r"""
const year = arguments[0];
const isShown = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
const headings = Array.from(document.querySelectorAll('h2, h3, h4'))
    .filter(h => (h.textContent || '').replace(/\s+/g, ' ').trim() === year && isShown(h));
for (const heading of headings) {
    let el = heading.parentElement;
    for (let level = 0; level < 5 && el; level++, el = el.parentElement) {
        if (el.querySelector('.company-history-rich')) return el;
    }
}
return null;
"""


def _is_year(token: str) -> bool:
    """
    :param token: Первое слово текста кнопки.
    :return: True, если это четырёхзначный год.
    """
    return token.isdigit() and len(token) == 4 and 1900 <= int(token) <= 2100


class NeoflexAboutOfHistoryPageParser(NeoflexPageParser):
    """
    Парсер страницы «История компании» neoflex.ru.

    Страница — интерактивная временная шкала: сверху карусель годов,
    ниже — блок деталей активного года (заголовок-год, краткий текст,
    свёрнутый блок «Подробнее» с расширенными фактами).

    Особенности реализации:
      - карусель годов реализована через CSS transform + overflow-x-clip,
        поэтому текст кнопок читается через textContent в JS;
      - год активируется программным click через JS с предварительным
        scrollIntoView, чтобы кнопка попала в clip-контейнер;
      - блок «Подробнее» не требует клика: расширенный контент
        (.company-history-rich--more) уже присутствует в DOM, свёрнут
        только через grid-rows-[0fr] + overflow-hidden — outerHTML его
        захватывает.
    """

    _HEADER_XPATH = (
        "//*[self::h1 or self::h2 or self::h3][normalize-space(.)='История компании']"
    )

    # Стратегии поиска контейнера карусели с годами в порядке приоритета.
    _TIMELINE_STRATEGIES: tuple[Strategy, ...] = (
        (By.CSS_SELECTOR, ".company-history__timeline"),
        (By.CSS_SELECTOR, "section.company-history"),
        (By.XPATH, "//section[.//*[normalize-space(.)='История компании']]"),
    )

    def parse(self) -> str:
        """
        Парсит страницу «История компании».

        :return: Markdown: заголовок и детали каждого года.
        """
        self._load_page()

        parts: list[str | None] = [self._parse_header()]

        years = self._collect_years()
        logger.info("История: найдено годов: %d %s", len(years), years)
        parts.extend(self._parse_year(year) for year in years)

        return self._join_parts(parts)

    def _parse_header(self) -> str | None:
        """
        :return: Markdown видимого заголовка страницы или None.
        """
        header = self._find_displayed(By.XPATH, self._HEADER_XPATH, context="заголовок «История компании»")
        if header is None:
            logger.warning("Заголовок 'История компании' не найден на %s", self._url)
            return None
        return self._element_markdown(header, context="заголовок «История компании»")

    def _timeline(self) -> WebElement | None:
        """
        :return: Контейнер карусели с годами или None.
        """
        return self._find_first(self._TIMELINE_STRATEGIES, context="карусель годов")

    def _collect_years(self) -> list[str]:
        """
        :return: Годы из карусели без дублей в порядке появления.
        """
        timeline = self._timeline()
        if timeline is None:
            logger.warning("Карусель годов не найдена на %s", self._url)
            return []

        texts = self._safe_js(_BUTTON_TEXTS_JS, timeline, context="годы карусели", default=[]) or []
        tokens = (text.split()[0] for text in texts if text)
        return list(dict.fromkeys(token for token in tokens if _is_year(token)))

    def _parse_year(self, year: str) -> str | None:
        """
        Извлекает детали одного года.

        :param year: Год из карусели.
        :return: Markdown деталей или None, если год не активировался или детали не найдены.
        """
        if not self._activate_year(year):
            return None

        detail = self._safe_js(_FIND_DETAIL_JS, year, context=f"детали года {year}")
        if detail is None:
            logger.warning("Не найден контейнер деталей для года %s на %s", year, self._url)
            return None

        return self._element_markdown(
            detail, context=f"год {year}", tags_to_remove=DEFAULT_STRIP_TAGS,
        )

    def _activate_year(self, year: str) -> bool:
        """
        Кликает по кнопке года и ждёт, пока деталь покажет нужный год.

        :param year: Год из карусели.
        :return: True, если деталь обновилась; False при любой неудаче.
        """
        timeline = self._timeline()
        buttons = []
        if timeline is not None:
            buttons = self._safe_js(
                _FIND_YEAR_BUTTONS_JS, timeline, year,
                context=f"кнопка года {year}", default=[],
            ) or []
        if not buttons:
            logger.warning("Кнопка года %s не найдена на %s", year, self._url)
            return False

        if not self._safe_js(_CLICK_JS, buttons[0], context=f"клик по году {year}", default=False):
            return False

        return self._wait_for(
            lambda driver: self._detail_ready(driver, year),
            context=f"детали года {year}",
        )

    @staticmethod
    def _detail_ready(driver: WebDriver, year: str) -> bool:
        """
        Условие для WebDriverWait: виден заголовок h2/h3/h4 с текстом, равным году.

        :param driver: WebDriver, передаваемый WebDriverWait.
        :param year: Ожидаемый год.
        :return: True, если такой заголовок виден.
        """
        xpath = f"//*[self::h2 or self::h3 or self::h4][normalize-space(.)='{year}']"
        try:
            return any(el.is_displayed() for el in driver.find_elements(By.XPATH, xpath))
        except StaleElementReferenceException:
            # Страница перерисовывается между опросами — это штатно, ждём дальше.
            return False
