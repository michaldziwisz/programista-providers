from __future__ import annotations

import json
import threading
import time as time_module
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any
from urllib.parse import urlparse

from tvguide_app.core.http import HttpClient
from tvguide_app.core.models import AccessibilityFeature, ProviderId, ScheduleItem, Source, SourceId
from tvguide_app.core.providers.base import ScheduleProvider
from tvguide_app.core.util import clean_multiline_text, clean_text


TVP_PROGRAM_URL = "https://www.tvp.pl/program-tv"


class TvpAccessibilityProvider(ScheduleProvider):
    def __init__(self, http: HttpClient) -> None:
        self._http = http
        self._lock = threading.RLock()
        self._day_cache: dict[str, _TvpDayCache] = {}

    @property
    def provider_id(self) -> str:
        return "tvp"

    @property
    def display_name(self) -> str:
        return "Telewizja (TVP)"

    def list_sources(self, *, force_refresh: bool = False) -> list[Source]:
        html = self._http.get_text(
            f"{TVP_PROGRAM_URL}?date={date.today().isoformat()}",
            cache_key="tvp:program:stations",
            ttl_seconds=7 * 24 * 3600,
            force_refresh=force_refresh,
            timeout_seconds=20.0,
        )
        stations = parse_tvp_stations(html)
        return [
            Source(provider_id=ProviderId(self.provider_id), id=SourceId(st.slug), name=st.name)
            for st in stations
        ]

    def list_days(self, *, force_refresh: bool = False) -> list[date]:
        today = date.today()
        return [today + timedelta(days=i) for i in range(14)]

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
                    return cached.by_station.get(str(source.id), [])

        built = self._build_day_cache(day, force_refresh=force_refresh)
        with self._lock:
            self._day_cache[day_key] = built
        return built.by_station.get(str(source.id), [])

    def get_item_details(self, item: ScheduleItem, *, force_refresh: bool = False) -> str:  # noqa: ARG002
        return item.details_summary or item.title

    def _build_day_cache(self, day: date, *, force_refresh: bool) -> "_TvpDayCache":
        day_key = day.isoformat()
        html = self._http.get_text(
            f"{TVP_PROGRAM_URL}?date={day_key}",
            cache_key=f"tvp:program:{day_key}",
            ttl_seconds=6 * 3600,
            force_refresh=force_refresh,
            timeout_seconds=20.0,
        )
        schedules = parse_tvp_program_page(html)

        by_station: dict[str, list[ScheduleItem]] = {}
        for sch in schedules:
            station_src = Source(
                provider_id=ProviderId(self.provider_id),
                id=SourceId(sch.station.slug),
                name=sch.station.name,
            )
            items = sorted(sch.items, key=lambda it: it.start_ms)
            out: list[ScheduleItem] = []
            for it in items:
                out.append(
                    ScheduleItem(
                        provider_id=ProviderId(self.provider_id),
                        source=station_src,
                        day=day,
                        start_time=ms_to_local_time(it.start_ms),
                        end_time=ms_to_local_time(it.end_ms) if it.end_ms else None,
                        title=it.title,
                        subtitle=None,
                        details_ref=None,
                        details_summary=it.description,
                        accessibility=tuple(it.accessibility),
                    )
                )
            by_station[sch.station.slug] = out

        return _TvpDayCache(expires_at=time_module.time() + 6 * 3600, by_station=by_station)


@dataclass(frozen=True)
class _TvpStation:
    slug: str
    name: str


@dataclass(frozen=True)
class _TvpItem:
    start_ms: int
    end_ms: int | None
    title: str
    description: str | None
    accessibility: list[AccessibilityFeature]


@dataclass(frozen=True)
class _TvpStationSchedule:
    station: _TvpStation
    items: list[_TvpItem]


@dataclass(frozen=True)
class _TvpDayCache:
    expires_at: float
    by_station: dict[str, list[ScheduleItem]]


def parse_tvp_stations(html: str) -> list[_TvpStation]:
    schedules = parse_tvp_program_page(html)
    stations: list[_TvpStation] = []
    for sch in schedules:
        stations.append(sch.station)
    seen: set[str] = set()
    out: list[_TvpStation] = []
    for st in stations:
        if st.slug in seen:
            continue
        seen.add(st.slug)
        out.append(st)
    out.sort(key=lambda s: s.name.casefold())
    return out


def parse_tvp_program_page(html: str) -> list[_TvpStationSchedule]:
    decoder = json.JSONDecoder()
    schedules: list[_TvpStationSchedule] = []
    pos = 0
    while True:
        idx = html.find("window.__stationsProgram[", pos)
        if idx == -1:
            break
        eq = html.find("=", idx)
        if eq == -1:
            break
        brace = html.find("{", eq)
        if brace == -1:
            pos = eq + 1
            continue
        try:
            obj, end = decoder.raw_decode(html[brace:])
        except json.JSONDecodeError:
            pos = brace + 1
            continue
        pos = brace + end

        schedule = _parse_station_schedule(obj)
        if schedule:
            schedules.append(schedule)
    return schedules


def _parse_station_schedule(obj: Any) -> _TvpStationSchedule | None:
    if not isinstance(obj, dict):
        return None
    station_raw = obj.get("station")
    if not isinstance(station_raw, dict):
        return None
    url = station_raw.get("url")
    name = station_raw.get("name")
    if not isinstance(url, str) or not url.strip() or not isinstance(name, str) or not name.strip():
        return None

    slug = _station_slug_from_url(url)
    if not slug:
        return None

    items_raw = obj.get("items")
    if not isinstance(items_raw, list):
        items_raw = []

    items: list[_TvpItem] = []
    for it in items_raw:
        parsed = _parse_item(it)
        if parsed:
            items.append(parsed)

    return _TvpStationSchedule(station=_TvpStation(slug=slug, name=_normalize_station_name(name)), items=items)


def _parse_item(it: Any) -> _TvpItem | None:
    if not isinstance(it, dict):
        return None
    start_ms = it.get("date_start")
    end_ms = it.get("date_end")
    title = it.get("title")
    if not isinstance(start_ms, int) or not isinstance(title, str) or not title.strip():
        return None
    if end_ms is not None and not isinstance(end_ms, int):
        end_ms = None

    accessibility: list[AccessibilityFeature] = []
    if it.get("ad") is True:
        accessibility.append("AD")
    if it.get("jm") is True:
        accessibility.append("JM")
    if it.get("nt") is True:
        accessibility.append("N")

    description = None
    program = it.get("program")
    if isinstance(program, dict):
        desc = program.get("description_long") or program.get("description")
        if isinstance(desc, str) and desc.strip():
            description = clean_multiline_text(desc)

    return _TvpItem(
        start_ms=start_ms,
        end_ms=end_ms,
        title=clean_text(title),
        description=description,
        accessibility=accessibility,
    )


def _station_slug_from_url(url: str) -> str:
    try:
        path = urlparse(url).path
    except Exception:  # noqa: BLE001
        return ""
    parts = [p for p in path.split("/") if p]
    if not parts:
        return ""
    return parts[-1]


def _normalize_station_name(name: str) -> str:
    name = clean_text(name)
    if name.startswith("TVP") and len(name) > 3 and name[3:].isdigit():
        return "TVP " + name[3:]
    return name


def ms_to_local_time(ts_ms: int) -> time:
    return datetime.fromtimestamp(ts_ms / 1000).time().replace(microsecond=0)
