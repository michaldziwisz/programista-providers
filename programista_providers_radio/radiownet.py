from __future__ import annotations

import json
import threading
import time as time_module
from dataclasses import dataclass
from datetime import date, time, timedelta
from html import unescape

from bs4 import BeautifulSoup

from tvguide_app.core.http import HttpClient
from tvguide_app.core.models import ProviderId, ScheduleItem, Source, SourceId
from tvguide_app.core.providers.base import ScheduleProvider
from tvguide_app.core.util import clean_multiline_text, clean_text, parse_time_hhmm


RADIOWNET_URL = "https://wnet.fm/ramowka"
RADIOWNET_SOURCE_ID = "radiownet"

_RADIOWNET_DAY_INDEX = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


@dataclass(frozen=True)
class _RadioWnetProgramme:
    start: time | None
    end: time | None
    title: str
    details: str


@dataclass(frozen=True)
class _RadioWnetWeekCache:
    expires_at: float
    by_weekday: dict[int, list[_RadioWnetProgramme]]


class RadioWnetProvider(ScheduleProvider):
    def __init__(self, http: HttpClient) -> None:
        self._http = http
        self._lock = threading.RLock()
        self._cache: _RadioWnetWeekCache | None = None

    @property
    def provider_id(self) -> str:
        return "radiownet"

    @property
    def display_name(self) -> str:
        return "Radio Wnet"

    def list_sources(self, *, force_refresh: bool = False) -> list[Source]:  # noqa: ARG002
        return [
            Source(
                provider_id=ProviderId(self.provider_id),
                id=SourceId(RADIOWNET_SOURCE_ID),
                name="Radio Wnet",
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
        if str(source.id) != RADIOWNET_SOURCE_ID:
            return []

        programmes = self._get_week_schedule(force_refresh=force_refresh).get(day.weekday(), [])
        return [
            ScheduleItem(
                provider_id=ProviderId(self.provider_id),
                source=source,
                day=day,
                start_time=programme.start,
                end_time=programme.end,
                title=programme.title,
                subtitle=None,
                details_ref=None,
                details_summary=programme.details or None,
            )
            for programme in programmes
        ]

    def get_item_details(self, item: ScheduleItem, *, force_refresh: bool = False) -> str:  # noqa: ARG002
        return item.details_summary or item.title

    def _get_week_schedule(self, *, force_refresh: bool) -> dict[int, list[_RadioWnetProgramme]]:
        if not force_refresh:
            with self._lock:
                if self._cache and self._cache.expires_at > time_module.time():
                    return self._cache.by_weekday

        html = self._http.get_text(
            RADIOWNET_URL,
            cache_key="radiownet:ramowka",
            ttl_seconds=6 * 3600,
            force_refresh=force_refresh,
            timeout_seconds=20.0,
        )
        by_weekday = parse_radiownet_schedule_html(html)

        with self._lock:
            self._cache = _RadioWnetWeekCache(
                expires_at=time_module.time() + 6 * 3600,
                by_weekday=by_weekday,
            )
        return by_weekday


def parse_radiownet_schedule_html(html: str) -> dict[int, list[_RadioWnetProgramme]]:
    raw_json = extract_radiownet_all_slots_json(html)
    if not raw_json:
        return {}

    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, list):
        return {}

    by_weekday: dict[int, list[_RadioWnetProgramme]] = {}
    for raw in data:
        if not isinstance(raw, dict):
            continue

        day_name = clean_text(raw.get("day_of_week") or "").casefold()
        weekday = _RADIOWNET_DAY_INDEX.get(day_name)
        if weekday is None:
            continue

        audycja = raw.get("audycja")
        if not isinstance(audycja, dict):
            continue

        title = _clean_radiownet_text(audycja.get("title"))
        if not title:
            continue

        start_time = _parse_radiownet_time(raw.get("start_time"))
        end_time = _parse_radiownet_time(raw.get("end_time"))

        hosts = _extract_radiownet_hosts(audycja.get("hosts"))
        content = _clean_radiownet_text(audycja.get("content"))
        excerpt = _clean_radiownet_text(audycja.get("excerpt"))

        details_parts: list[str] = []
        if hosts:
            details_parts.append(f"Prowadzący: {', '.join(hosts)}")
        if content:
            details_parts.append(content)
        elif excerpt:
            details_parts.append(excerpt)

        details = "\n\n".join(details_parts)
        by_weekday.setdefault(weekday, []).append(
            _RadioWnetProgramme(
                start=start_time,
                end=end_time,
                title=title,
                details=details,
            )
        )

    for weekday, programmes in by_weekday.items():
        programmes.sort(key=lambda programme: programme.start or time.min)
        by_weekday[weekday] = programmes

    return by_weekday


def extract_radiownet_all_slots_json(html: str) -> str:
    needle = '\\"allSlots\\":['
    start = html.find(needle)
    if start == -1:
        return ""

    array_start = html.find("[", start)
    if array_start == -1:
        return ""

    in_string = False
    escape = False
    depth = 0
    array_end: int | None = None

    for index, char in enumerate(html[array_start:], start=array_start):
        if escape:
            escape = False
            continue
        if char == "\\":
            escape = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                array_end = index + 1
                break

    if array_end is None:
        return ""

    escaped_json = html[array_start:array_end]
    try:
        return json.loads(f'"{escaped_json}"')
    except json.JSONDecodeError:
        return ""


def _parse_radiownet_time(value: object) -> time | None:
    text = clean_text(value or "")
    if not text:
        return None
    try:
        return parse_time_hhmm(text)
    except Exception:  # noqa: BLE001
        return None


def _extract_radiownet_hosts(value: object) -> list[str]:
    if not isinstance(value, list):
        return []

    hosts: list[str] = []
    seen: set[str] = set()
    for raw in value:
        if not isinstance(raw, dict):
            continue
        name = _clean_radiownet_text(raw.get("name"))
        if not name:
            continue
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        hosts.append(name)
    return hosts


def _clean_radiownet_text(value: object) -> str:
    if value is None:
        return ""

    text = str(value)
    if not text:
        return ""

    # Content mixes JSON escapes with HTML entities like &#8211; / &nbsp;.
    for _ in range(2):
        text = unescape(text)
    text = text.replace("\xa0", " ")

    if "<" in text and ">" in text:
        text = BeautifulSoup(text, "lxml").get_text("\n")

    return clean_multiline_text(text)
