"""Парсер страницы «Наши контакты» neoflex.ru."""

import logging
from .base import NeoflexPageParser
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.common.exceptions import StaleElementReferenceException, WebDriverException


logger = logging.getLogger(__name__)


# Убираем <noscript> и счётчик Яндекс.Метрики.
_REMOVE_NOISE_JS = r"""
document.querySelectorAll('noscript').forEach(el => el.remove());
document.querySelectorAll('img[src*="mc.yandex.ru"]').forEach(el => el.remove());
return true;
"""

# Названия городов: кнопки в ближайшем контейнере заголовка (кроме <footer>).
_COLLECT_CITIES_JS = r"""
const heading = Array.from(document.querySelectorAll('h1, h2, h3'))
    .find(h => (h.textContent || '').trim() === arguments[0]);
if (!heading) return [];
let container = heading.parentElement;
while (container && container.querySelectorAll('button').length === 0) {
    container = container.parentElement;
}
if (!container) return [];
return Array.from(container.querySelectorAll('button'))
    .filter(b => !b.closest('footer'))
    .map(b => (b.textContent || '').trim())
    .filter(t => t.length > 0);
"""

_FIND_CITY_BUTTON_JS = r"""
return Array.from(document.querySelectorAll('button'))
    .find(b => (b.textContent || '').trim() === arguments[0]) || null;
"""

# Активная кнопка города получает класс md:font-bold (состояние React).
_IS_BUTTON_ACTIVE_JS = r"""
const btn = Array.from(document.querySelectorAll('button'))
    .find(b => (b.textContent || '').trim() === arguments[0]);
return !!btn && /\bmd:font-bold\b/.test(btn.className);
"""

# Карточка деталей — ближайший ancestor иконки адреса, содержащий также иконку
# email. Пара address и email есть у всех городов; метро и машины — только у
# Москвы (блок «Как добраться?»), поэтому полагаться на них нельзя.
_FIND_CARD_JS = r"""
let el = document.querySelector(arguments[0]);
while (el) {
    if (el.querySelector(arguments[1])) return el;
    el = el.parentElement;
}
return null;
"""


class NeoflexContactsPageParser(NeoflexPageParser):
    """
    Парсер страницы «Наши контакты» neoflex.ru.

    Страница устроена как переключатель городов:
      - заголовок «Наши контакты» (h2);
      - сетка кнопок-городов;
      - карточка деталей активного города: адрес, телефоны, email;
        у Москвы дополнительно — блок «Как добраться?».

    Парсер последовательно кликает по каждой кнопке-городу, дожидается
    переключения содержимого карточки и собирает Markdown.
    После клика сначала ждём смены активного класса на кнопке (индикатор
    обновления состояния React), затем — обновления карточки.
    """

    _TITLE_TEXT = "Наши контакты"

    _ADDRESS_ICON = 'img[src*="/contacts-icons/address.svg"]'
    _EMAIL_ICON = 'img[src*="/contacts-icons/email.svg"]'

    def parse(self) -> str:
        """
        Парсит страницу «Наши контакты».

        :return: Markdown: заголовок и карточка каждого города.
        """
        self._load_page()
        self._safe_js(_REMOVE_NOISE_JS, context="шум страницы контактов")

        title_md = self._extract_title()

        cities = self._collect_cities()
        logger.info("Контакты: найдено городов: %s", cities)

        parts: list[str] = []
        for city in cities:
            city_md = self._parse_city(city)
            if city_md:
                parts.append(f"## {city}\n\n{city_md}")

        return self._join_parts([title_md, *parts])

    def _extract_title(self) -> str | None:
        """
        :return: Заголовок «Наши контакты» как H1 или None, если видимого заголовка нет.
        """
        title = self._find_displayed(
            By.XPATH,
            f"//*[self::h1 or self::h2 or self::h3][normalize-space(.)='{self._TITLE_TEXT}']",
            context="заголовок «Наши контакты»",
        )
        if title is None:
            logger.warning("Заголовок '%s' не найден на %s", self._TITLE_TEXT, self._url)
            return None
        return f"# {self._TITLE_TEXT}"

    def _collect_cities(self) -> list[str]:
        """
        :return: Названия городов из кнопок-переключателей без дублей.
        """
        cities = self._safe_js(
            _COLLECT_CITIES_JS, self._TITLE_TEXT, context="список городов", default=[],
        ) or []
        return list(dict.fromkeys(cities))

    def _parse_city(self, city: str) -> str | None:
        """
        Извлекает карточку деталей одного города.

        :param city: Название города.
        :return: Markdown карточки или None, если город не активировался или карточка не найдена.
        """
        if not self._activate_city(city):
            return None

        card = self._find_details_card()
        if card is None:
            logger.warning("Карточка деталей не найдена для города %s на %s", city, self._url)
            return None

        # В карточке все <img> — иконки (адрес, телефон, email, у Москвы ещё
        # метро и машины). Удаляем их, текст остаётся.
        return self._element_markdown(card, context=f"контакты {city}", tags_to_remove=("img",))

    def _activate_city(self, city: str) -> bool:
        """
        Кликает по кнопке города и ждёт обновления состояния и карточки.

        :param city: Название города.
        :return: True, если кнопка стала активной и карточка обновилась.
        """
        button = self._safe_js(_FIND_CITY_BUTTON_JS, city, context=f"кнопка города {city}")
        if button is None:
            logger.warning("Кнопка города %s не найдена на %s", city, self._url)
            return False

        self._safe_js(
            "arguments[0].scrollIntoView({block: 'center'});", button,
            context=f"прокрутка к городу {city}",
        )
        if not self._click(button, city):
            return False

        return (
            self._wait_for(
                lambda _: self._is_button_active(city),
                context=f"активная кнопка города {city}",
            )
            and self._wait_for(
                lambda _: self._card_mentions_city(city),
                context=f"карточка города {city}",
            )
        )

    def _click(self, button: WebElement, city: str) -> bool:
        """
        Кликает по кнопке нативно, при неудаче — через JS.

        :param button: Кнопка города.
        :param city: Название города (для лога).
        :return: True, если клик выполнен.
        """
        try:
            button.click()
            return True
        except WebDriverException as exc:
            logger.debug("Нативный клик по %s не удался (%s), пробуем JS", city, exc.msg)
        return bool(self._safe_js(
            "arguments[0].click(); return true;", button,
            context=f"JS-клик по городу {city}", default=False,
        ))

    def _is_button_active(self, city: str) -> bool:
        """
        :param city: Название города.
        :return: True, если кнопка города найдена и активна.
        """
        return bool(self._safe_js(
            _IS_BUTTON_ACTIVE_JS, city, context=f"состояние кнопки {city}", default=False,
        ))

    def _card_mentions_city(self, city: str) -> bool:
        """
        Работает для всех текущих городов («г. Москва», «г.Санкт-Петербург» и т.д.):
        все адреса содержат название города как подстроку.

        :param city: Название города.
        :return: True, если название города найдено в тексте карточки деталей.
        """
        card = self._find_details_card()
        if card is None:
            return False
        try:
            return city in (card.get_attribute("textContent") or "")
        except StaleElementReferenceException:
            # Карточка перерисована между опросами — это штатно, ждём дальше.
            return False

    def _find_details_card(self) -> WebElement | None:
        """
        :return: Карточка деталей активного города или None.
        """
        return self._safe_js(
            _FIND_CARD_JS, self._ADDRESS_ICON, self._EMAIL_ICON,
            context="карточка деталей города",
        )
