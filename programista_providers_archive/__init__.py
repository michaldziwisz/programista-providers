from __future__ import annotations

from datetime import date

from tvguide_app.core.http import HttpClient
from tvguide_app.core.providers.archive_base import ArchiveProvider

from programista_providers_archive.fandom_archive import FandomArchiveProvider


def load(http: HttpClient) -> list[ArchiveProvider]:
    return [FandomArchiveProvider(http, year=date.today().year)]

