from __future__ import annotations

from tvguide_app.core.http import HttpClient
from tvguide_app.core.providers.base import ScheduleProvider

from programista_providers_radio.polskieradio import PolskieRadioProvider
from programista_providers_radio.radiokierowcow import RadioKierowcowProvider
from programista_providers_radio.nowyswiat import NowySwiatProvider
from programista_providers_radio.radio357 import Radio357Provider
from programista_providers_radio.radioolsztyn import RadioOlsztynProvider
from programista_providers_radio.radiopoznan import RadioPoznanProvider
from programista_providers_radio.radiowroclaw import RadioWroclawProvider
from programista_providers_radio.tokfm import TokFmProvider


def load(http: HttpClient) -> list[ScheduleProvider]:
    return [
        PolskieRadioProvider(http),
        RadioKierowcowProvider(http),
        NowySwiatProvider(http),
        Radio357Provider(http),
        RadioOlsztynProvider(http),
        RadioPoznanProvider(http),
        RadioWroclawProvider(http),
        TokFmProvider(http),
    ]
