from __future__ import annotations

from tvguide_app.core.http import HttpClient
from tvguide_app.core.providers.base import ScheduleProvider

from programista_providers_tv_accessibility.polsat import PolsatAccessibilityProvider
from programista_providers_tv_accessibility.puls import PulsAccessibilityProvider
from programista_providers_tv_accessibility.tvp import TvpAccessibilityProvider


def load(http: HttpClient) -> list[ScheduleProvider]:
    return [
        TvpAccessibilityProvider(http),
        PolsatAccessibilityProvider(http),
        PulsAccessibilityProvider(http),
    ]

