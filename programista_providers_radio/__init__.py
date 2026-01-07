from __future__ import annotations

from tvguide_app.core.http import HttpClient
from tvguide_app.core.providers.base import ScheduleProvider

from programista_providers_radio.polskieradio import PolskieRadioProvider
from programista_providers_radio.radiokierowcow import RadioKierowcowProvider
from programista_providers_radio.nowyswiat import NowySwiatProvider


def load(http: HttpClient) -> list[ScheduleProvider]:
    return [
        PolskieRadioProvider(http),
        RadioKierowcowProvider(http),
        NowySwiatProvider(http),
    ]
