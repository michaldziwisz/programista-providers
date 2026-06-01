from __future__ import annotations

from tvguide_app.core.http import HttpClient
from tvguide_app.core.providers.base import ScheduleProvider

from programista_providers_tv.kanalzero import KanalZeroProvider
from programista_providers_tv.teleman import TelemanProvider
from programista_providers_tv.tvp_extra import TvpExtraTvProvider
from programista_providers_tv.tvp_vod_live import TvpVodLiveProvider
from programista_providers_tv.wpolsce24 import Wpolsce24Provider


def load(http: HttpClient) -> list[ScheduleProvider]:
    return [
        TelemanProvider(http),
        TvpVodLiveProvider(http),
        TvpExtraTvProvider(http),
        Wpolsce24Provider(http),
        KanalZeroProvider(http),
    ]
