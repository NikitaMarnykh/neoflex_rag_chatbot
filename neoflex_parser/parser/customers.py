"""Парсер страницы «Клиенты» neoflex.ru."""

import re
import logging
from .base import NeoflexPageParser
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver


logger = logging.getLogger(__name__)


# Готовность сетки: в контейнере страницы есть хотя бы одна карточка
# с непустым alt. Контейнер ищется от заголовка «Наши клиенты» вверх —
# так селектор не зависит от tailwind-классов сетки.
_GRID_READY_JS = r"""
const heading = Array.from(document.querySelectorAll('h1, h2, h3'))
    .find(h => (h.textContent || '').trim() === arguments[0]);
if (!heading) return false;
let container = heading.parentElement;
while (container) {
    for (const img of container.querySelectorAll('img[alt]')) {
        if ((img.alt || '').trim()) return true;
    }
    container = container.parentElement;
}
return false;
"""

# Сырые alt'ы логотипов в контейнере сетки. Контейнер — ближайший предок
# заголовка, содержащий ≥ 2 img[alt]: одиночный логотип в хедере не зацепится.
_COLLECT_ALTS_JS = r"""
const heading = Array.from(document.querySelectorAll('h1, h2, h3'))
    .find(h => (h.textContent || '').trim() === arguments[0]);
if (!heading) return [];
let container = heading.parentElement;
while (container) {
    const imgs = container.querySelectorAll('img[alt]');
    if (imgs.length >= 2) {
        return Array.from(imgs)
            .map(img => (img.alt || '').trim())
            .filter(Boolean);
    }
    container = container.parentElement;
}
return [];
"""

# Номера страниц пагинации: кнопки с текстом из 1–3 цифр вне хедера и футера.
_COLLECT_PAGES_JS = r"""
const seen = new Set();
const result = [];
document.querySelectorAll('button').forEach(btn => {
    if (btn.closest('header, footer')) return;
    const t = (btn.textContent || '').trim();
    if (!/^\d{1,3}$/.test(t)) return;
    const n = parseInt(t, 10);
    if (n >= 1 && n <= 50 && !seen.has(n)) {
        seen.add(n);
        result.push(n);
    }
});
result.sort((a, b) => a - b);
return result;
"""

# Клик по кнопке страницы по точному числовому textContent.
_CLICK_PAGE_JS = r"""
const btn = Array.from(document.querySelectorAll('button'))
    .find(b => (b.textContent || '').trim() === arguments[0]);
if (!btn) return false;
btn.click();
return true;
"""

# Текущая активная страница: кнопка, у которой текст — цифра и есть
# класс text-[#259AFF] (подсветка активной). Используется только для лога.
_ACTIVE_PAGE_JS = r"""
const btn = Array.from(document.querySelectorAll('button'))
    .find(b => /^\d{1,3}$/.test((b.textContent || '').trim())
               && /text-\[#259AFF\]/.test(b.className));
return btn ? parseInt((btn.textContent || '').trim(), 10) : null;
"""


class NeoflexCustomersPageParser(NeoflexPageParser):
    """
    Парсер страницы «Клиенты» neoflex.ru (/about/customers).

    Страница — пагинированный каталог логотипов клиентов с фильтром по отраслям:
      - заголовок «Наши клиенты» (h2);
      - фильтр «Все отрасли / Финансы / Промышленность / Ритейл»;
      - сетка карточек-логотипов (16 на страницу, 4 страницы);
      - пагинация «1 2 3 4» + стрелки «назад/вперёд».

    Имя клиента присутствует только в alt-атрибуте <img> внутри карточки;
    другого текста в DOM нет. Поэтому сбор клиентов идёт через alt логотипов
    с нормализацией и отбрасыванием мусорных значений (только хеш без имени).

    Пагинация клиентская: URL не меняется, сетка перерисовывается через
    React state. Парсер последовательно кликает по каждой доступной странице,
    собирает alt'ы и дедуплицирует клиентов. Фильтр отраслей не трогается —
    по умолчанию открыт «Все отрасли».

    Устойчивость к вёрстке:
      - заголовок ищется по тексту h2/h1, а не по классу;
      - карточки — по наличию <img alt> в ближайшем предке заголовка, а не
        по tailwind-классам вида w-[calc((100%_-_40px)/3)];
      - кнопки пагинации ищутся по короткому числовому textContent
        вне <header>/<footer>, кнопки фильтров отсекаются автоматически
        (нецифровой текст);
      - после клика по странице ждём смены набора alt'ов — индикатора
        обновления React state. Если набор не изменился (страница уже
        активна), это не считается ошибкой.
    """

    _TITLE_TEXT = "Наши клиенты"

    # Расширения файлов-логотипов и типичные суффиксы alt'ов.
    _EXT_RE = re.compile(r"\.(?:png|jpe?g|webp|svg|gif)$", re.IGNORECASE)
    _SCALE_RE = re.compile(r"([_-])(\d+x|\d+)$", re.IGNORECASE)
    _LOGO_SUFFIX_RE = re.compile(r"(logo|logotype)$", re.IGNORECASE)
    _LOGO_PREFIX_RE = re.compile(r"^logo[_\-\s]+", re.IGNORECASE)
    _HASH_RE = re.compile(r"^[0-9a-f]{16,}$", re.IGNORECASE)
    _SEP_RE = re.compile(r"[_\-]+")

    def parse(self) -> str:
        """
        Парсит страницу «Клиенты».

        :return: Markdown: заголовок и список клиентов.
        """
        self._load_page()
        self._wait_for(self._grid_ready, context="сетка клиентов")

        title_md = self._parse_title()

        seen: set[str] = set()
        clients: list[str] = []

        for page in self._collect_page_numbers():
            if not self._activate_page(page):
                continue
            for name in self._collect_clients_on_page():
                if name not in seen:
                    seen.add(name)
                    clients.append(name)

        if not clients:
            logger.warning("Клиенты не найдены на %s", self._url)
            return self._join_parts([title_md])

        body_md = "\n".join(f"- {name}" for name in clients)
        return self._join_parts([title_md, body_md])

    # --- Заголовок ---

    def _parse_title(self) -> str | None:
        """
        :return: Заголовок «Наши клиенты» как H1 или None, если заголовок не найден.
        """
        if self._find_displayed(
            By.XPATH,
            f"//*[self::h1 or self::h2 or self::h3][normalize-space(.)='{self._TITLE_TEXT}']",
            context="заголовок «Наши клиенты»",
        ) is None:
            logger.warning("Заголовок '%s' не найден на %s", self._TITLE_TEXT, self._url)
            return None
        return f"# {self._TITLE_TEXT}"

    # --- Готовность сетки ---

    def _grid_ready(self, driver: WebDriver) -> bool:
        """
        Условие для WebDriverWait: есть хотя бы одна карточка с непустым alt.

        :param driver: WebDriver, передаваемый WebDriverWait.
        :return: True, если сетка отрисована.
        """
        return bool(self._safe_js(
            _GRID_READY_JS, self._TITLE_TEXT,
            context="готовность сетки клиентов", default=False,
        ))

    # --- Пагинация ---

    def _collect_page_numbers(self) -> list[int]:
        """
        :return: Номера страниц пагинации по возрастанию; пустой список, если не найдены.
        """
        numbers = self._safe_js(
            _COLLECT_PAGES_JS, context="номера страниц пагинации", default=[],
        ) or []
        return [int(n) for n in numbers]

    def _activate_page(self, page: int) -> bool:
        """
        Кликает по кнопке страницы и ждёт, пока React перерисует сетку.

        Если набор alt'ов не изменился (страница уже была активной),
        это не считается ошибкой: сбор клиентов с текущей страницы
        всё равно даст корректный результат.

        :param page: Номер страницы.
        :return: True, если клик выполнен; False при неудаче.
        """
        before = tuple(self._collect_raw_alts())

        clicked = self._safe_js(
            _CLICK_PAGE_JS, str(page),
            context=f"клик по странице {page}", default=False,
        )
        if not clicked:
            logger.warning("Кнопка страницы %s не найдена на %s", page, self._url)
            return False

        # Ждём смены набора alt'ов. Если страница уже активна — набор
        # не изменится, тайм-аут залогируется, но это штатный сценарий.
        self._wait_for(
            lambda _: tuple(self._collect_raw_alts()) != before,
            context=f"обновление сетки после перехода на страницу {page}",
        )
        return True

    # --- Сбор клиентов ---

    def _collect_raw_alts(self) -> list[str]:
        """
        :return: Сырые alt'ы логотипов в сетке (без нормализации).
        """
        return self._safe_js(
            _COLLECT_ALTS_JS, self._TITLE_TEXT,
            context="alt'ы логотипов клиентов", default=[],
        ) or []

    def _collect_clients_on_page(self) -> list[str]:
        """
        Собирает имена клиентов на текущей странице из alt логотипов.

        :return: Список имён клиентов без неинформативных alt'ов.
        """
        result: list[str] = []
        for raw in self._collect_raw_alts():
            cleaned = self._clean_logo_alt(raw)
            if cleaned is None:
                logger.debug(
                    "Пропускаю логотип с неинформативным alt: %r на %s",
                    raw, self._url,
                )
                continue
            result.append(cleaned)
        return result

    @classmethod
    def _clean_logo_alt(cls, raw: str) -> str | None:
        """
        Превращает alt логотипа в человекочитаемое имя клиента.

        Alt'ы на сайте заполнены вразнобой: «atomayz.png», «AkBars_1x.png»,
        «logo-russ.jpg», «88acbf30cbf4b63f1895551c830c3df3.png». Расширение,
        масштаб (1x/2x), префикс/суффикс «logo» отбрасываются; чисто
        хешевые значения без имени возвращают None — восстановить клиента
        по ним нельзя, и в RAG они не должны попасть.

        :param raw: Alt-атрибут картинки.
        :return: Имя клиента или None, если alt неинформативен.
        """
        text = (raw or "").strip()
        if not text:
            return None

        stem = cls._EXT_RE.sub("", text)
        stem = cls._SCALE_RE.sub("", stem)
        stem = cls._LOGO_SUFFIX_RE.sub("", stem)
        stem = cls._LOGO_PREFIX_RE.sub("", stem)

        if cls._HASH_RE.fullmatch(stem):
            return None

        stem = cls._SEP_RE.sub(" ", stem)
        stem = re.sub(r"\s+", " ", stem).strip()
        if not stem:
            return None

        # Уже смешанный регистр («AkBars», «SBI») не трогаем, чтобы
        # не ломать брендовые написания.
        return " ".join(
            word if any(c.isupper() for c in word) else word.capitalize()
            for word in stem.split()
        )
