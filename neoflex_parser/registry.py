"""Роутинг URL."""

from urllib.parse import urlsplit
from .parser import (
    NeoflexAboutOfCareerPageParser,
    NeoflexAboutOfCompanyPageParser,
    NeoflexAboutOfHistoryPageParser,
    NeoflexAboutOfPartnersPageParser,
    NeoflexContactsPageParser,
    NeoflexIndustriesPageParser,
    NeoflexMainPageParser,
    NeoflexPageParser,
    NeoflexPlatformsPageParser,
    NeoflexPressArticlePageParser,
    NeoflexProjectsPageParser,
    NeoflexServicesPageParser,
)


EXACT_PARSERS: dict[str, type[NeoflexPageParser]] = {
    "/": NeoflexMainPageParser,
    "/about/company": NeoflexAboutOfCompanyPageParser,
    "/about/history": NeoflexAboutOfHistoryPageParser,
    "/about/partners": NeoflexAboutOfPartnersPageParser,
    "/about/career": NeoflexAboutOfCareerPageParser,
    "/contacts": NeoflexContactsPageParser,
}

PREFIX_PARSERS: dict[str, type[NeoflexPageParser]] = {
    "/projects/": NeoflexProjectsPageParser,
    "/industries/": NeoflexIndustriesPageParser,
    "/services/": NeoflexServicesPageParser,
    "/platforms/": NeoflexPlatformsPageParser,
    "/news/": NeoflexPressArticlePageParser,
    "/publications/": NeoflexPressArticlePageParser,
}


def resolve_parser_class(url: str) -> type[NeoflexPageParser] | None:
    """
    :param url: URL страницы.
    :return: Класс парсера или None, если для URL парсера нет.
    """
    # Приводим путь к каноническому виду без завершающего слэша, чтобы
    # "/about/company/" и "/about/company" попадали в один и тот же парсер.
    # Пустой путь (например, "https://site.ru") превращаем в "/".
    path = urlsplit(url).path.rstrip("/") or "/"
    # Сначала проверяем точные совпадения: они имеют приоритет над префиксами,
    # чтобы, например, "/about/company" не ушёл в общий префиксный парсер.
    exact = EXACT_PARSERS.get(path)
    if exact is not None:
        return exact
    # Затем — префиксные маршруты для разделов с динамическими сегментами.
    for prefix, cls in PREFIX_PARSERS.items():
        if path.startswith(prefix):
            return cls
    return None