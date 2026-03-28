from __future__ import annotations

from tvguide_app.core.http import HttpClient
from tvguide_app.core.providers.base import ScheduleProvider

from programista_providers_radio.polskieradio import PolskieRadioProvider
from programista_providers_radio.polskieradio_chopin import PolskieRadioChopinProvider
from programista_providers_radio.polskieradio_dzieciom import PolskieRadioDzieciomProvider
from programista_providers_radio.radiokierowcow import RadioKierowcowProvider
from programista_providers_radio.radiobialystok import RadioBialystokProvider
from programista_providers_radio.radiokielce import RadioKielceProvider
from programista_providers_radio.nowyswiat import NowySwiatProvider
from programista_providers_radio.radio357 import Radio357Provider
from programista_providers_radio.radiolublin import RadioLublinProvider
from programista_providers_radio.radioolsztyn import RadioOlsztynProvider
from programista_providers_radio.radiopoznan import RadioPoznanProvider
from programista_providers_radio.radiownet import RadioWnetProvider
from programista_providers_radio.radiowroclaw import RadioWroclawProvider
from programista_providers_radio.radiogdansk import RadioGdanskProvider
from programista_providers_radio.radiokatowice import RadioKatowiceProvider
from programista_providers_radio.radioszczecin import RadioSzczecinProvider
from programista_providers_radio.radiozet import RadioZetProvider
from programista_providers_radio.radiozachod import RadioZachodProvider
from programista_providers_radio.rmfclassic import RmfClassicProvider
from programista_providers_radio.rmf24 import Rmf24Provider
from programista_providers_radio.rmffm import RmfFmProvider
from programista_providers_radio.tokfm import TokFmProvider


def load(http: HttpClient) -> list[ScheduleProvider]:
    return [
        PolskieRadioProvider(http),
        PolskieRadioChopinProvider(http),
        PolskieRadioDzieciomProvider(http),
        RadioKierowcowProvider(http),
        RadioBialystokProvider(http),
        RadioKielceProvider(http),
        RadioLublinProvider(http),
        NowySwiatProvider(http),
        Radio357Provider(http),
        RadioOlsztynProvider(http),
        RadioPoznanProvider(http),
        RadioWnetProvider(http),
        RadioWroclawProvider(http),
        RadioGdanskProvider(http),
        RadioKatowiceProvider(http),
        RadioSzczecinProvider(http),
        RadioZetProvider(http),
        RadioZachodProvider(http),
        RmfClassicProvider(http),
        Rmf24Provider(http),
        RmfFmProvider(http),
        TokFmProvider(http),
    ]
