"""Парсеры страниц neoflex.ru."""

from .base import DEFAULT_STRIP_TAGS, NeoflexPageParser
from .career import NeoflexAboutOfCareerPageParser
from .company import NeoflexAboutOfCompanyPageParser
from .contacts import NeoflexContactsPageParser
from .history import NeoflexAboutOfHistoryPageParser
from .main_page import NeoflexMainPageParser
from .partners import NeoflexAboutOfPartnersPageParser
from .press import NeoflexPressArticlePageParser
from .projects import NeoflexProjectsPageParser
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
]
