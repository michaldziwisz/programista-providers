from __future__ import annotations

import threading
import time as time_module
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from bs4 import BeautifulSoup

from tvguide_app.core.http import HttpClient
from tvguide_app.core.models import AccessibilityFeature, ProviderId, ScheduleItem, Source, SourceId
from tvguide_app.core.providers.base import ScheduleProvider
from tvguide_app.core.util import clean_text


POLSAT_MODULE_URL = "https://www.polsat.pl/tv-html/module/page{page}/"


class PolsatAccessibilityProvider(ScheduleProvider):
    def __init__(self, http: HttpClient) -> None:
        self._http = http
        self._lock = threading.RLock()
        self._day_cache: dict[str, _PolsatDayCache] = {}

    @property
    def provider_id(self) -> str:
        return "polsat"

    @property
    def display_name(self) -> str:
        return "Telewizja (Polsat)"

    def list_sources(self, *, force_refresh: bool = False) -> list[Source]:
        html = self._fetch_module(1, force_refresh=force_refresh)
        channels = parse_polsat_channels_from_module(html)
        return [
            Source(provider_id=ProviderId(self.provider_id), id=SourceId(ch.id), name=ch.name)
            for ch in channels
        ]

    def list_days(self, *, force_refresh: bool = False) -> list[date]:  # noqa: ARG002
        today = date.today()
        return [today + timedelta(days=i) for i in range(7)]

    def get_schedule(
        self,
        source: Source,
        day: date,
        *,
        force_refresh: bool = False,
    ) -> list[ScheduleItem]:
        day_key = day.isoformat()
        if not force_refresh:
            with self._lock:
                cached = self._day_cache.get(day_key)
                if cached and cached.expires_at > time_module.time():
                    return cached.by_channel.get(str(source.id), [])

        built = self._build_day_cache(day, force_refresh=force_refresh)
        with self._lock:
            self._day_cache[day_key] = built
        return built.by_channel.get(str(source.id), [])

    def get_item_details(self, item: ScheduleItem, *, force_refresh: bool = False) -> str:  # noqa: ARG002
        return item.title

    def _build_day_cache(self, day: date, *, force_refresh: bool) -> "_PolsatDayCache":
        page = (day - date.today()).days + 1
        if page < 1 or page > 7:
            return _PolsatDayCache(expires_at=time_module.time() + 60 * 30, by_channel={})

        html = self._fetch_module(page, force_refresh=force_refresh)
        parsed = parse_polsat_day_from_module(html, day=day)
        return _PolsatDayCache(expires_at=time_module.time() + 60 * 30, by_channel=parsed)

    def _fetch_module(self, page: int, *, force_refresh: bool) -> str:
        url = POLSAT_MODULE_URL.format(page=page)
        return self._http.get_text(
            url,
            cache_key=f"polsat:module:{page}",
            ttl_seconds=60 * 30,
            force_refresh=force_refresh,
            timeout_seconds=20.0,
        )


@dataclass(frozen=True)
class _PolsatChannel:
    id: str
    name: str


@dataclass(frozen=True)
class _PolsatItem:
    start_time: time
    end_time: time | None
    title: str
    accessibility: list[AccessibilityFeature]
    start_ms: int


def parse_polsat_channels_from_module(html: str) -> list[_PolsatChannel]:
    soup = BeautifulSoup(html, "lxml")
    channels: list[_PolsatChannel] = []
    for row in soup.select("div.tv__row[data-channel]"):
        channel = clean_text(row.get("data-channel") or "")
        if not channel:
            continue
        channels.append(_PolsatChannel(id=channel, name=channel))
    seen: set[str] = set()
    out: list[_PolsatChannel] = []
    for ch in channels:
        if ch.id in seen:
            continue
        seen.add(ch.id)
        out.append(ch)
    out.sort(key=lambda c: c.name.casefold())
    return out


def parse_polsat_schedule_from_module(html: str, *, channel: str) -> list[_PolsatItem]:
    soup = BeautifulSoup(html, "lxml")
    row = soup.find("div", {"class": "tv__row", "data-channel": channel})
    if not row:
        return []

    return _parse_polsat_row_items(row)


def parse_polsat_day_from_module(html: str, *, day: date) -> dict[str, list[ScheduleItem]]:
    soup = BeautifulSoup(html, "lxml")
    out: dict[str, list[ScheduleItem]] = {}

    for row in soup.select("div.tv__row[data-channel]"):
        channel = clean_text(row.get("data-channel") or "")
        if not channel:
            continue

        items = _parse_polsat_row_items(row)
        if not items:
            continue

        src = Source(provider_id=ProviderId("polsat"), id=SourceId(channel), name=channel)
        sch: list[ScheduleItem] = []
        for it in items:
            sch.append(
                ScheduleItem(
                    provider_id=ProviderId("polsat"),
                    source=src,
                    day=day,
                    start_time=it.start_time,
                    end_time=it.end_time,
                    title=it.title,
                    subtitle=None,
                    details_ref=None,
                    details_summary=None,
                    accessibility=tuple(it.accessibility),
                )
            )
        out[channel] = sch
    return out


def _parse_polsat_row_items(row: BeautifulSoup) -> list[_PolsatItem]:
    items: list[_PolsatItem] = []
    for cast in row.select("div.tvcast[data-start][data-end]"):
        start_ms_s = cast.get("data-start") or ""
        end_ms_s = cast.get("data-end") or ""
        if not start_ms_s.isdigit() or not end_ms_s.isdigit():
            continue
        start_ms = int(start_ms_s)
        end_ms = int(end_ms_s)
        title_el = cast.select_one(".tvcast__title")
        title = clean_text(title_el.get_text(" ")) if title_el else ""
        if not title:
            continue

        accessibility: list[AccessibilityFeature] = []
        for icon in cast.select(".tvcast__accesibility-icon"):
            text = clean_text(icon.get_text(" ")).upper()
            title_attr = clean_text(icon.get("title") or "").casefold()
            if text == "AD" or "audiodeskrypcja" in title_attr:
                accessibility.append("AD")
            elif text == "JM" or "język migowy" in title_attr or "jezyk migowy" in title_attr:
                accessibility.append("JM")
            elif text == "N" or "napisy" in title_attr:
                accessibility.append("N")

        start_time = datetime.fromtimestamp(start_ms / 1000).time().replace(microsecond=0)
        end_time = datetime.fromtimestamp(end_ms / 1000).time().replace(microsecond=0)

        items.append(
            _PolsatItem(
                start_time=start_time,
                end_time=end_time,
                title=title,
                accessibility=_uniq(accessibility),
                start_ms=start_ms,
            )
        )

    items.sort(key=lambda it: it.start_ms)
    # De-duplicate (the grid may repeat the same programme in multiple cells).
    seen: set[tuple[int, str]] = set()
    out: list[_PolsatItem] = []
    for it in items:
        key = (it.start_ms, it.title)
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


def _uniq(features: list[AccessibilityFeature]) -> list[AccessibilityFeature]:
    seen: set[AccessibilityFeature] = set()
    out: list[AccessibilityFeature] = []
    for f in features:
        if f in seen:
            continue
        seen.add(f)
        out.append(f)
    return out


@dataclass(frozen=True)
class _PolsatDayCache:
    expires_at: float
    by_channel: dict[str, list[ScheduleItem]]
