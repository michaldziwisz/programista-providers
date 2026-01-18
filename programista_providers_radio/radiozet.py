from __future__ import annotations

import json
import threading
import time as time_module
from dataclasses import dataclass
from datetime import date, time, timedelta

from tvguide_app.core.http import HttpClient
from tvguide_app.core.models import ProviderId, ScheduleItem, Source, SourceId
from tvguide_app.core.providers.base import ScheduleProvider
from tvguide_app.core.util import clean_text


RADIOZET_STATION_ID = "radiozet"
RADIOZET_SCHEDULE_URL_TEMPLATE = (
    "https://player.radiozet.pl/api/"
    + RADIOZET_STATION_ID
    + "-radio/schedule-for-day/(day)/{day}/(station)/"
    + RADIOZET_STATION_ID
)


@dataclass(frozen=True)
class _RadioZetProgramme:
    start: time | None
    end: time | None
    title: str
    details: str


@dataclass(frozen=True)
class _RadioZetDayCache:
    expires_at: float
    programmes: list[_RadioZetProgramme]


class RadioZetProvider(ScheduleProvider):
    def __init__(self, http: HttpClient) -> None:
        self._http = http
        self._lock = threading.RLock()
        self._cache_by_weekday: dict[int, _RadioZetDayCache] = {}

    @property
    def provider_id(self) -> str:
        return "radiozet"

    @property
    def display_name(self) -> str:
        return "Radio ZET"

    def list_sources(self, *, force_refresh: bool = False) -> list[Source]:  # noqa: ARG002
        return [
            Source(
                provider_id=ProviderId(self.provider_id),
                id=SourceId("radiozet"),
                name="Radio ZET",
            )
        ]

    def list_days(self, *, force_refresh: bool = False) -> list[date]:  # noqa: ARG002
        today = date.today()
        return [today + timedelta(days=i) for i in range(14)]

    def get_schedule(
        self,
        source: Source,
        day: date,
        *,
        force_refresh: bool = False,
    ) -> list[ScheduleItem]:
        if str(source.id) != "radiozet":
            return []

        # API expects 0..6 (Mon..Sun).
        weekday = day.isoweekday() - 1  # Monday=0..Sunday=6
        programmes = self._get_day_programmes(weekday, force_refresh=force_refresh)
        return [
            ScheduleItem(
                provider_id=ProviderId(self.provider_id),
                source=source,
                day=day,
                start_time=p.start,
                end_time=p.end,
                title=p.title,
                subtitle=None,
                details_ref=None,
                details_summary=p.details or None,
            )
            for p in programmes
        ]

    def get_item_details(self, item: ScheduleItem, *, force_refresh: bool = False) -> str:  # noqa: ARG002
        # No separate details endpoint; we embed what we have in details_summary.
        return item.details_summary or item.title

    def _get_day_programmes(self, weekday: int, *, force_refresh: bool) -> list[_RadioZetProgramme]:
        if not force_refresh:
            with self._lock:
                cached = self._cache_by_weekday.get(weekday)
                if cached and cached.expires_at > time_module.time():
                    return cached.programmes

        url = RADIOZET_SCHEDULE_URL_TEMPLATE.format(day=weekday)
        json_text = self._http.get_text(
            url,
            cache_key=f"radiozet:ramowka:v1:{weekday}",
            ttl_seconds=6 * 3600,
            force_refresh=force_refresh,
            timeout_seconds=20.0,
        )
        programmes = parse_radiozet_schedule_json(json_text)
        if programmes:
            with self._lock:
                self._cache_by_weekday[weekday] = _RadioZetDayCache(
                    expires_at=time_module.time() + 6 * 3600,
                    programmes=programmes,
                )
        return programmes


def parse_radiozet_schedule_json(text: str) -> list[_RadioZetProgramme]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []

    parsed: list[tuple[int | None, _RadioZetProgramme]] = []

    for raw in data:
        if not isinstance(raw, dict):
            continue

        program = raw.get("program")
        if not isinstance(program, dict):
            continue
        title = clean_text(str(program.get("name") or ""))
        if not title:
            continue

        start_sec = _parse_int(raw.get("start"))
        end_sec = _parse_int(raw.get("end"))

        # Some items use 86400 to represent 00:00 (sorted as the last item).
        # Normalize times for display and ordering.
        start_norm = (start_sec % 86400) if start_sec is not None else None
        end_norm = (end_sec % 86400) if end_sec is not None else None

        presenters: list[str] = []
        people = raw.get("people")
        if isinstance(people, list):
            for person in people:
                if not isinstance(person, dict):
                    continue
                name = clean_text(str(person.get("name") or ""))
                if name:
                    presenters.append(name)
        details = ", ".join(_uniq_strings(presenters))

        programme = _RadioZetProgramme(
            start=_seconds_to_time(start_norm) if start_norm is not None else None,
            end=_seconds_to_time(end_norm) if end_norm is not None else None,
            title=title,
            details=details,
        )
        parsed.append((start_norm, programme))

    parsed.sort(key=lambda x: (x[0] is None, x[0] if x[0] is not None else 0))

    seen: set[tuple[str, str]] = set()
    out: list[_RadioZetProgramme] = []
    for start_norm, p in parsed:
        key = (f"{start_norm:05d}" if start_norm is not None else "", p.title.casefold())
        if key in seen:
            continue
        seen.add(key)
        out.append(p)

    return out


def _parse_int(value) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _seconds_to_time(seconds: int) -> time:
    seconds = max(0, seconds)
    hours = (seconds // 3600) % 24
    minutes = (seconds % 3600) // 60
    return time(int(hours), int(minutes))


def _uniq_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for v in values:
        key = v.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(v)
    return out

