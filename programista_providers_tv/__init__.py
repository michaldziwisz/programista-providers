from __future__ import annotations

from tvguide_app.core.http import HttpClient
from tvguide_app.core.providers.base import ScheduleProvider

from programista_providers_tv.teleman import TelemanProvider


def load(http: HttpClient) -> list[ScheduleProvider]:
    return [TelemanProvider(http)]

