from __future__ import annotations

from tvguide_app.core.http import HttpClient
from tvguide_app.core.providers.base import ScheduleProvider

from programista_providers_radio.polskieradio import PolskieRadioProvider
from programista_providers_radio.radiokierowcow import RadioKierowcowProvider


def load(http: HttpClient) -> list[ScheduleProvider]:
    return [
        PolskieRadioProvider(http),
        RadioKierowcowProvider(http),
    ]
