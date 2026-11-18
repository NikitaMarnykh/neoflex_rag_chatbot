"""Парсеры страниц neoflex.ru."""


from .main_page import NeoflexMainPageParser
from .contacts import NeoflexContactsPageParser
from .projects import NeoflexProjectsPageParser
from .press import NeoflexPressArticlePageParser
from .customers import NeoflexCustomersPageParser
from .career import NeoflexAboutOfCareerPageParser
from .company import NeoflexAboutOfCompanyPageParser
from .history import NeoflexAboutOfHistoryPageParser
from .partners import NeoflexAboutOfPartnersPageParser
from .base import DEFAULT_STRIP_TAGS, NeoflexPageParser
from .semantic import (
    NeoflexIndustriesPageParser,
    NeoflexPlatformsPageParser,
    NeoflexServicesPageParser,
)

__all__ = [
    "DEFAULT_STRIP_TAGS",
    "NeoflexAboutOfCareerPageParser",
    "NeoflexAboutOfCompanyPageParser",
    "NeoflexAboutOfHistoryPageParser",
    "NeoflexAboutOfPartnersPageParser",
    "NeoflexContactsPageParser",
    "NeoflexIndustriesPageParser",
    "NeoflexMainPageParser",
    "NeoflexPageParser",
    "NeoflexPlatformsPageParser",
    "NeoflexPressArticlePageParser",
    "NeoflexProjectsPageParser",
    "NeoflexServicesPageParser",
    "NeoflexCustomersPageParser",
]
