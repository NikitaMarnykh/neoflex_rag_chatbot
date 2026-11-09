"""Базовый класс парсеров страниц neoflex.ru и общие помощники."""

import logging
from markdownify import markdownify
from abc import ABC, abstractmethod
from typing import Any, Callable, Iterable, Sequence
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.common.exceptions import TimeoutException, WebDriverException


logger = logging.getLogger(__name__)

# Стратегия поиска элемента: (By.XPATH / By.CSS_SELECTOR, значение).
Strategy = tuple[str, str]

# Теги, которые удаляются при конвертации: URL и картинки не нужны в Markdown.
DEFAULT_STRIP_TAGS: tuple[str, ...] = ("a", "img")

# Медиа и иконки: в Markdown бесполезны, удаляются при чистке любой секции.
MEDIA_SELECTORS: tuple[str, ...] = ("picture", "img", "video", "source", "svg")

# Чистка DOM секции перед конвертацией в Markdown.
# arguments[0] — корневой элемент, arguments[1] — опции:
#   remove         — CSS-селекторы удаляемых элементов;
#   dropTexts      — <a>/<span> с таким точным текстом удаляются целиком (CTA «Подробнее»);
#   splitBr        — <p> с <br><br> разбиваются на отдельные <p>, иначе markdownify
#                    склеит несколько абзацев в один;
#   collapsePasses — число проходов, схлопывающих опустевшие <div>-обёртки
#                    (многоуровневые обёртки убираются только за несколько проходов).
# Ссылки разворачиваются в содержимое: URL не нужен, а вложенные <h3>/<p> сохраняются.
CLEAN_SECTION_JS = r"""
const root = arguments[0];
const opts = arguments[1];
const textOf = el => (el.textContent || '').trim();

opts.remove.forEach(sel => root.querySelectorAll(sel).forEach(el => el.remove()));

const dropTexts = new Set(opts.dropTexts);
if (dropTexts.size) {
    root.querySelectorAll('a, span').forEach(el => {
        if (dropTexts.has(textOf(el))) el.remove();
    });
}

if (opts.splitBr) {
    const doubleBr = /<br\s*\/?>\s*<br\s*\/?>/i;
    Array.from(root.querySelectorAll('p'))
        .filter(p => p.parentNode && doubleBr.test(p.innerHTML))
        .forEach(p => {
            p.innerHTML.split(doubleBr).forEach(part => {
                if (!part.trim()) return;
                const np = document.createElement('p');
                np.innerHTML = part;
                p.parentNode.insertBefore(np, p);
            });
            p.remove();
        });
}

root.querySelectorAll('a').forEach(a => {
    if (!a.parentNode) return;
    while (a.firstChild) a.parentNode.insertBefore(a.firstChild, a);
    a.remove();
});

// div с кнопками и полями ввода не трогаем.
const keep = 'button, input, textarea, select';
for (let i = 0; i < opts.collapsePasses; i++) {
    root.querySelectorAll('div').forEach(d => {
        if (!textOf(d) && !d.querySelector(keep)) d.remove();
    });
}
return true;
"""

# Секция по тексту её h2: ближайшая <section> или родитель заголовка.
FIND_SECTION_BY_H2_JS = r"""
const target = arguments[0];
for (const h2 of document.querySelectorAll('h2')) {
    const t = (h2.textContent || '').replace(/\s+/g, ' ').trim();
    if (t === target) return h2.closest('section') || h2.parentElement;
}
return null;
"""


class NeoflexPageParser(ABC):
    """
    Абстрактный базовый класс парсеров страниц neoflex.ru.

    Содержит общие операции над Selenium WebDriver: загрузку страницы,
    поиск элементов по цепочке стратегий, чистку DOM, выполнение JavaScript
    и конвертацию HTML в Markdown. Наследники реализуют метод parse().

    Все операции, где WebDriver может вернуть ошибку, логируют её на уровне
    WARNING с URL страницы и названием блока: тихая потеря блока или
    недочищенный DOM означают мусор или дыру в корпусе для RAG.
    """

    def __init__(self, driver: WebDriver, url: str, timeout: float = 30) -> None:
        """
        Инициализирует парсер.

        :param driver: Selenium WebDriver, через который выполняется работа со страницей.
        :param url: Адрес страницы, которую необходимо распарсить.
        :param timeout: Максимальное время ожиданий в секундах.
        """
        self._driver = driver
        self._url = url
        # Один WebDriverWait на все методы ожидания.
        self._wait = WebDriverWait(driver, timeout)

    @abstractmethod
    def parse(self) -> str:
        """
        Парсит страницу. Обязателен для реализации в наследниках.

        :return: Содержимое страницы в виде Markdown.
        """

    # --- Загрузка и ожидания ---

    def _load_page(self) -> None:
        """Загружает страницу по URL и ждёт полной загрузки DOM."""
        self._driver.get(self._url)
        self._wait.until(lambda d: d.execute_script("return document.readyState") == "complete")

    def _wait_for(self, condition: Callable[[WebDriver], Any], *, context: str) -> bool:
        """
        Ждёт выполнения условия.

        :param condition: Условие для WebDriverWait.
        :param context: Что ожидается (для лога).
        :return: True, если условие выполнилось; False при тайм-ауте.
        """
        try:
            self._wait.until(condition)
        except TimeoutException:
            logger.warning("Тайм-аут ожидания: %s на %s", context, self._url)
            return False
        return True

    # --- JavaScript ---

    def _safe_js(self, script: str, *args: Any, context: str, default: Any = None) -> Any:
        """
        Выполняет JavaScript; ошибку WebDriver логирует и возвращает default.

        :param script: JavaScript-код.
        :param args: Аргументы, доступные в скрипте через arguments.
        :param context: Что делает скрипт (для лога).
        :param default: Значение, возвращаемое при ошибке.
        :return: Результат скрипта или default.
        """
        try:
            return self._driver.execute_script(script, *args)
        except WebDriverException as exc:
            logger.warning("Ошибка JS (%s) на %s: %s", context, self._url, exc.msg)
            return default

    def _clean(
        self,
        root: WebElement,
        *,
        context: str,
        remove: Iterable[str] = (),
        drop_texts: Iterable[str] = (),
        split_br: bool = False,
        collapse_passes: int = 5,
    ) -> None:
        """
        Чистит DOM секции (см. CLEAN_SECTION_JS). Медиа удаляются всегда.

        :param root: Корневой элемент секции.
        :param context: Название секции (для лога).
        :param remove: Дополнительные CSS-селекторы удаляемых элементов.
        :param drop_texts: Тексты <a>/<span>, удаляемых целиком.
        :param split_br: Разбивать ли <p> с <br><br>.
        :param collapse_passes: Число проходов схлопывания пустых div.
        """
        options = {
            "remove": [*MEDIA_SELECTORS, *remove],
            "dropTexts": list(drop_texts),
            "splitBr": split_br,
            "collapsePasses": collapse_passes,
        }
        self._safe_js(CLEAN_SECTION_JS, root, options, context=f"чистка DOM «{context}»")

    # --- Поиск ---

    def _find_all_first(self, strategies: Iterable[Strategy], *, context: str) -> list[WebElement]:
        """
        Ищет элементы по цепочке стратегий.

        :param strategies: Пары (стратегия поиска, значение) в порядке приоритета.
        :param context: Что ищется (для лога).
        :return: Результат первой стратегии, нашедшей элементы; иначе пустой список.
        """
        for by, value in strategies:
            try:
                found = self._driver.find_elements(by, value)
            except WebDriverException as exc:
                logger.warning(
                    "Поиск «%s» (%s=%r) упал на %s: %s",
                    context, by, value, self._url, exc.msg,
                )
                continue
            if found:
                return found
        return []

    def _find_first(self, strategies: Iterable[Strategy], *, context: str) -> WebElement | None:
        """
        :param strategies: Пары (стратегия поиска, значение) в порядке приоритета.
        :param context: Что ищется (для лога).
        :return: Первый найденный элемент или None.
        """
        found = self._find_all_first(strategies, context=context)
        return found[0] if found else None

    def _find_displayed(self, by: str, value: str, *, context: str) -> WebElement | None:
        """
        :param by: Стратегия поиска.
        :param value: Селектор или XPath.
        :param context: Что ищется (для лога).
        :return: Первый видимый элемент или None.
        """
        try:
            for element in self._driver.find_elements(by, value):
                if element.is_displayed():
                    return element
        except WebDriverException as exc:
            logger.warning("Поиск «%s» упал на %s: %s", context, self._url, exc.msg)
        return None

    def _find_section_by_h2(self, text: str) -> WebElement | None:
        """
        :param text: Текст h2 (с нормализованными пробелами).
        :return: Ближайшая <section> или родитель h2; None, если h2 не найден.
        """
        return self._safe_js(FIND_SECTION_BY_H2_JS, text, context=f"секция «{text}»")

    # --- Markdown ---

    @staticmethod
    def _to_markdown(html: str, tags_to_remove: Sequence[str] | None = None) -> str:
        """
        Конвертирует HTML в Markdown.

        :param html: Исходный HTML.
        :param tags_to_remove: Теги, которые нужно удалить перед конвертацией.
        :return: Строка в формате Markdown.
        """
        strip = list(tags_to_remove) if tags_to_remove else None
        # ATX-заголовки: «## Заголовок» вместо подчёркивания.
        return markdownify(str(html), heading_style="ATX", strip=strip)

    def _element_markdown(
        self,
        element: WebElement,
        *,
        context: str,
        tags_to_remove: Sequence[str] | None = None,
    ) -> str | None:
        """
        Конвертирует outerHTML элемента в Markdown.

        :param element: Элемент страницы.
        :param context: Название блока (для лога).
        :param tags_to_remove: Теги, которые нужно удалить перед конвертацией.
        :return: Markdown или None, если HTML не прочитался.
        """
        try:
            html = element.get_attribute("outerHTML")
        except WebDriverException as exc:
            logger.warning("Не прочитан HTML «%s» на %s: %s", context, self._url, exc.msg)
            return None
        if not html:
            return None
        return self._to_markdown(html, tags_to_remove=tags_to_remove).strip()

    def _block_markdown(
        self,
        strategies: Iterable[Strategy],
        *,
        context: str,
        tags_to_remove: Sequence[str] | None = None,
    ) -> str | None:
        """
        Находит блок по цепочке стратегий и конвертирует его в Markdown.

        :param strategies: Пары (стратегия поиска, значение) в порядке приоритета.
        :param context: Название блока (для лога).
        :param tags_to_remove: Теги, которые нужно удалить перед конвертацией.
        :return: Markdown или None, если блок не найден или не прочитался.
        """
        element = self._find_first(strategies, context=context)
        if element is None:
            logger.warning("Блок «%s» не найден на %s", context, self._url)
            return None
        return self._element_markdown(element, context=context, tags_to_remove=tags_to_remove)

    def _extract_section(
        self,
        find: Callable[[], WebElement | None],
        *,
        context: str,
        tags_to_remove: Sequence[str] | None = None,
        remove: Iterable[str] = (),
        drop_texts: Iterable[str] = (),
        split_br: bool = False,
        collapse_passes: int = 5,
    ) -> str | None:
        """
        Находит секцию, чистит её DOM и конвертирует в Markdown.

        :param find: Функция поиска секции (вызывается дважды: до и после чистки).
        :param context: Название секции (для лога).
        :param tags_to_remove: Теги, которые нужно удалить при конвертации.
        :param remove: Дополнительные CSS-селекторы удаляемых элементов.
        :param drop_texts: Тексты <a>/<span>, удаляемых целиком.
        :param split_br: Разбивать ли <p> с <br><br>.
        :param collapse_passes: Число проходов схлопывания пустых div.
        :return: Markdown или None, если секция не найдена, не прочиталась или пуста.
        """
        section = find()
        if section is None:
            logger.warning("Секция «%s» не найдена на %s", context, self._url)
            return None

        self._clean(
            section,
            context=context,
            remove=remove,
            drop_texts=drop_texts,
            split_br=split_br,
            collapse_passes=collapse_passes,
        )

        # После чистки DOM ссылка могла устареть (StaleElementReferenceException),
        # поэтому ищем элемент заново.
        section = find()
        if section is None:
            logger.warning("Секция «%s» исчезла после чистки DOM на %s", context, self._url)
            return None

        markdown = self._element_markdown(section, context=context, tags_to_remove=tags_to_remove)
        if not markdown:
            logger.warning("Секция «%s» дала пустой Markdown на %s", context, self._url)
            return None
        return markdown

    @staticmethod
    def _join_parts(parts: Iterable[str | None]) -> str:
        """
        Склеивает непустые части через пустую строку.

        :param parts: Строки или None; пустые значения пропускаются.
        :return: Объединённая строка.
        """
        return "\n\n".join(part for part in parts if part and part.strip())
