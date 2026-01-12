from __future__ import annotations

import json
import re
import threading
import time as time_module
from dataclasses import dataclass
from datetime import date, time, timedelta

from tvguide_app.core.http import HttpClient
from tvguide_app.core.models import ProviderId, ScheduleItem, Source, SourceId
from tvguide_app.core.providers.base import ScheduleProvider
from tvguide_app.core.util import clean_multiline_text, clean_text, parse_time_hhmm


RMF24_PAGE_URL = "https://www.rmf24.pl/radio"
RMF24_JSON_FALLBACK_URL = "https://www.rmf.fm/inc/outer/ramowka-rmf24-json/jsonfull2025.php"


@dataclass(frozen=True)
class _Rmf24Programme:
    start: time | None
    title: str
    details: str


@dataclass(frozen=True)
class _Rmf24WeekCache:
    expires_at: float
    by_day: dict[date, list[_Rmf24Programme]]


class Rmf24Provider(ScheduleProvider):
    def __init__(self, http: HttpClient) -> None:
        self._http = http
        self._lock = threading.RLock()
        self._week_cache: _Rmf24WeekCache | None = None

    @property
    def provider_id(self) -> str:
        return "rmf24"

    @property
    def display_name(self) -> str:
        return "RMF24"

    def list_sources(self, *, force_refresh: bool = False) -> list[Source]:  # noqa: ARG002
        return [
            Source(
                provider_id=ProviderId(self.provider_id),
                id=SourceId("rmf24"),
                name="Radio RMF24",
            )
        ]

    def list_days(self, *, force_refresh: bool = False) -> list[date]:
        week = self._get_week_map(force_refresh=force_refresh)
        days = sorted(week.keys())
        if days:
            return days

        today = date.today()
        return [today + timedelta(days=i) for i in range(7)]

    def get_schedule(
        self,
        source: Source,
        day: date,
        *,
        force_refresh: bool = False,
    ) -> list[ScheduleItem]:
        if str(source.id) != "rmf24":
            return []

        programmes = self._get_week_map(force_refresh=force_refresh).get(day, [])
        return [
            ScheduleItem(
                provider_id=ProviderId(self.provider_id),
                source=source,
                day=day,
                start_time=p.start,
                end_time=None,
                title=p.title,
                subtitle=None,
                details_ref=None,
                details_summary=p.details or None,
            )
            for p in programmes
        ]

    def get_item_details(self, item: ScheduleItem, *, force_refresh: bool = False) -> str:  # noqa: ARG002
        return item.details_summary or item.title

    def _get_week_map(self, *, force_refresh: bool) -> dict[date, list[_Rmf24Programme]]:
        if not force_refresh:
            with self._lock:
                if self._week_cache and self._week_cache.expires_at > time_module.time():
                    return self._week_cache.by_day

        page_html = self._http.get_text(
            RMF24_PAGE_URL,
            cache_key="rmf24:radio_page",
            ttl_seconds=24 * 3600,
            force_refresh=force_refresh,
            timeout_seconds=20.0,
        )
        json_url = extract_rmf24_schedule_url(page_html) or RMF24_JSON_FALLBACK_URL

        schedule_json = self._http.get_text(
            json_url,
            cache_key="rmf24:ramowka",
            ttl_seconds=60 * 30,
            force_refresh=force_refresh,
            timeout_seconds=20.0,
        )
        by_day = parse_rmf24_ramowka_json(schedule_json)

        with self._lock:
            self._week_cache = _Rmf24WeekCache(expires_at=time_module.time() + 60 * 30, by_day=by_day)
        return by_day


def extract_rmf24_schedule_url(page_html: str) -> str | None:
    m = re.search(r"\\bramFull\\s*=\\s*'([^']+)'", page_html)
    if m:
        return clean_text(m.group(1)).rstrip("?").split("?", 1)[0]

    m = re.search(r"https?://[^'\"\\s]+/ramowka-rmf24-json/jsonfull[^'\"\\s]*\\.php\\??", page_html)
    if m:
        return clean_text(m.group(0)).rstrip("?").split("?", 1)[0]

    return None


def parse_rmf24_ramowka_json(text: str) -> dict[date, list[_Rmf24Programme]]:
    json_text = _strip_jsonp(text)
    try:
        data = json.loads(json_text)
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}

    by_day: dict[date, list[_Rmf24Programme]] = {}
    for raw_day in data.values():
        if not isinstance(raw_day, dict):
            continue

        day_s = clean_text(str(raw_day.get("data") or ""))
        try:
            d = date.fromisoformat(day_s)
        except ValueError:
            continue

        programmes: list[_Rmf24Programme] = []
        raw_json = raw_day.get("json")
        if isinstance(raw_json, list):
            for block in raw_json:
                if not isinstance(block, dict):
                    continue
                raw_items = block.get("dni")
                if not isinstance(raw_items, list):
                    continue
                for raw in raw_items:
                    if not isinstance(raw, dict):
                        continue

                    title = clean_text(str(raw.get("program") or ""))
                    if not title:
                        continue

                    start_s = clean_text(str(raw.get("godzinaS") or ""))
                    start = parse_time_hhmm(start_s) if start_s else None

                    person = clean_text(str(raw.get("person") or ""))
                    notes = clean_multiline_text(str(raw.get("notes") or "")) if raw.get("notes") else ""
                    details = "\n\n".join([x for x in (person, notes) if x])

                    programmes.append(_Rmf24Programme(start=start, title=title, details=details))

        seen: set[tuple[str, str]] = set()
        deduped: list[_Rmf24Programme] = []
        for p in programmes:
            key = (p.start.strftime("%H:%M") if p.start else "", p.title.casefold())
            if key in seen:
                continue
            seen.add(key)
            deduped.append(p)

        by_day[d] = deduped

    return by_day


def _strip_jsonp(text: str) -> str:
    t = clean_text(text)
    if not t:
        return ""
    if t.startswith("{") or t.startswith("["):
        return text
    m = re.search(r"^[^(]+\\((.*)\\)\\s*;?\\s*$", text, flags=re.DOTALL)
    if not m:
        return text
    return m.group(1)
