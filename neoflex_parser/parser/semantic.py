"""Парсеры страниц отраслей, услуг и платформ neoflex.ru: hero + секции по h2."""

import logging
from functools import partial
from .base import DEFAULT_STRIP_TAGS, NeoflexPageParser

logger = logging.getLogger(__name__)

# Удаляет со страницы элементы по CSS-селекторам (arguments[0] — список).
_REMOVE_BY_SELECTOR_JS = r"""
arguments[0].forEach(sel => document.querySelectorAll(sel).forEach(el => el.remove()));
return true;
"""

# Заголовок h1 вне chrome и первый осмысленный подзаголовок секции hero.
# Кандидат на подзаголовок — не контейнер заголовка и не счётчик «01 / 05».
_HERO_JS = r"""
const h1 = Array.from(document.querySelectorAll('h1'))
    .find(el => !el.closest('header, footer, nav'));
if (!h1) return null;

const normalize = s => (s || '').replace(/\s+/g, ' ').trim();
const title = normalize(h1.textContent);
if (!title) return null;

const section = h1.closest('section') || h1.parentElement;
let subtitle = '';
if (section) {
    subtitle = Array.from(section.querySelectorAll('p, div.payload-richtext'))
        .filter(el => !el.contains(h1) && !el.closest('header, footer, nav, .page-navigation'))
        .map(el => normalize(el.textContent))
        .find(t => t && t !== title && !/^\d{2}\s*\/\s*\d{2}$/.test(t)) || '';
}
return { title, subtitle };
"""

# Тексты h2 вне chrome без дублей.
_COLLECT_H2_JS = r"""
const seen = new Set();
const result = [];
document.querySelectorAll('h2').forEach(h2 => {
    if (h2.closest('header, footer, nav')) return;
    const t = (h2.textContent || '').replace(/\s+/g, ' ').trim();
    if (t && !seen.has(t)) {
        seen.add(t);
        result.push(t);
    }
});
return result;
"""

# Интерактив и служебные теги: в Markdown не нужны.
_INTERACTIVE_TAGS: tuple[str, ...] = (
    "button", "form", "input", "textarea", "select", "script", "style", "noscript",
)


class _SemanticNeoflexParser(NeoflexPageParser):
    """
    Общая база для страниц, где контент собран из <section> и <h2>.

    Не привязана к классам вроде .expertises-detail или .platforms-detail.
    Ищет hero по <h1>, контентные секции — по <h2>, шумные секции отбрасывает
    по списку заголовков и CSS-селекторов. Наследники отличаются только
    документацией и маршрутом в registry.
    """

    # Тексты h2 служебных секций, которые не извлекаются.
    _NOISE_H2: frozenset[str] = frozenset({
        "Наши заказчики",
        "Истории успеха",
        "Новости и СМИ по теме",
    })

    # CSS-селекторы служебных блоков, которые удаляются со страницы.
    _NOISE_SELECTORS: tuple[str, ...] = (
        "header",
        "footer",
        "nav",
        "script",
        "style",
        "noscript",
        ".breadcrumbs",
        ".service__head-content-nav",
        ".service__clients",
        ".cases_elements",
        ".banner_link",
        ".news_elements",
        ".InfoBLock--news",
        ".slick-cloned",
    )

    # Теги, которые не нужны в Markdown (страховка на случай, если JS-чистка не сработала).
    _STRIP_TAGS: tuple[str, ...] = DEFAULT_STRIP_TAGS + (
        "picture", "source", "svg", "video",
        "button", "form", "input", "textarea", "select",
    )

    def parse(self) -> str:
        """
        Парсит страницу: hero и контентные секции по h2.

        :return: Markdown: hero-блок и контентные секции.
        """
        self._load_page()

        # Глобально убираем служебные блоки. Это безопасно:
        # hero и контент находятся не внутри header/footer/nav.
        self._safe_js(
            _REMOVE_BY_SELECTOR_JS, list(self._NOISE_SELECTORS),
            context="служебные блоки страницы",
        )

        parts: list[str | None] = [self._parse_hero()]
        parts.extend(
            self._extract_section(
                partial(self._find_section_by_h2, h2_text),
                context=h2_text,
                tags_to_remove=self._STRIP_TAGS,
                remove=(*self._NOISE_SELECTORS, *_INTERACTIVE_TAGS),
                # CTA-подписи «Подробнее» — метка, не несущая смысла.
                drop_texts=("Подробнее",),
            )
            for h2_text in self._collect_content_h2_texts()
        )
        return self._join_parts(parts)

    def _parse_hero(self) -> str | None:
        """
        :return: Markdown hero-блока или None, если h1 не найден или пуст.
        """
        data = self._safe_js(_HERO_JS, context="hero-блок")
        if not data:
            logger.warning("H1 не найден на %s", self._url)
            return None

        subtitle = (data.get("subtitle") or "").strip()
        return self._join_parts([f"# {data['title']}", subtitle])

    def _collect_content_h2_texts(self) -> list[str]:
        """
        :return: Тексты h2 контентных секций без дублей, без служебных.
        """
        texts = self._safe_js(_COLLECT_H2_JS, context="список h2", default=[]) or []
        return [text for text in texts if text not in self._NOISE_H2]


class NeoflexIndustriesPageParser(_SemanticNeoflexParser):
    """
    Парсер страниц отрасли neoflex.ru (/industries/<slug>).

    Страницы отраслей (Финансы, Промышленность, Ритейл): hero-блок с заголовком
    и подзаголовком, контентные секции с h2 («Для банков», «Решения»,
    «Платформы» и т.п.) и карточками решений. Служебные секции «Наши заказчики»,
    «Истории успеха», «Новости и СМИ по теме» и CTA-баннер не извлекаются.
    """


class NeoflexServicesPageParser(_SemanticNeoflexParser):
    """
    Парсер страниц услуг neoflex.ru (/services/<slug>).

    Контент собирается по h1/h2, а не по именам классов.
    Шумовые секции «Истории успеха» и «Новости и СМИ по теме» отбрасываются.
    """


class NeoflexPlatformsPageParser(_SemanticNeoflexParser):
    """
    Парсер страниц платформ neoflex.ru (/platforms/<slug>).

    Семантика страниц совпадает с услугами: hero и h2-секции.
    """
