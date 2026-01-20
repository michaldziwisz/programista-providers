from __future__ import annotations

import re
import threading
import time as time_module
from dataclasses import dataclass
from datetime import date, time, timedelta
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from tvguide_app.core.http import HttpClient
from tvguide_app.core.models import ProviderId, ScheduleItem, Source, SourceId
from tvguide_app.core.providers.base import ScheduleProvider
from tvguide_app.core.util import clean_text, parse_time_hhmm


RL_BASE = "https://radio.lublin.pl"
RL_SCHEDULE_URL = f"{RL_BASE}/ramowka/"


@dataclass(frozen=True)
class _RlublinProgramme:
    start: time | None
    end: time | None
    title: str
    details_ref: str | None


@dataclass(frozen=True)
class _RlublinWeekCache:
    expires_at: float
    by_weekday: dict[int, list[_RlublinProgramme]]


class RadioLublinProvider(ScheduleProvider):
    def __init__(self, http: HttpClient) -> None:
        self._http = http
        self._lock = threading.RLock()
        self._week_cache: _RlublinWeekCache | None = None

    @property
    def provider_id(self) -> str:
        return "radiolublin"

    @property
    def display_name(self) -> str:
        return "Radio Lublin"

    def list_sources(self, *, force_refresh: bool = False) -> list[Source]:  # noqa: ARG002
        return [
            Source(
                provider_id=ProviderId(self.provider_id),
                id=SourceId("lublin"),
                name="Radio Lublin",
            )
        ]

    def list_days(self, *, force_refresh: bool = False) -> list[date]:  # noqa: ARG002
        today = date.today()
        # The schedule is presented as a weekly grid (Mon..Sun), not tied to specific dates.
        # Expose only the upcoming week to avoid repeating the same pattern.
        return [today + timedelta(days=i) for i in range(7)]

    def get_schedule(
        self,
        source: Source,
        day: date,
        *,
        force_refresh: bool = False,
    ) -> list[ScheduleItem]:
        if str(source.id) != "lublin":
            return []

        weekday = day.isoweekday()  # Monday=1..Sunday=7
        programmes = self._get_week_map(force_refresh=force_refresh).get(weekday) or []
        return [
            ScheduleItem(
                provider_id=ProviderId(self.provider_id),
                source=source,
                day=day,
                start_time=p.start,
                end_time=p.end,
                title=p.title,
                subtitle=None,
                details_ref=p.details_ref,
                details_summary=None,
            )
            for p in programmes
        ]

    def get_item_details(self, item: ScheduleItem, *, force_refresh: bool = False) -> str:  # noqa: ARG002
        return item.details_summary or item.title

    def _get_week_map(self, *, force_refresh: bool) -> dict[int, list[_RlublinProgramme]]:
        if not force_refresh:
            with self._lock:
                if self._week_cache and self._week_cache.expires_at > time_module.time():
                    return self._week_cache.by_weekday

        html = self._http.get_text(
            RL_SCHEDULE_URL,
            cache_key="rlublin:ramowka",
            ttl_seconds=6 * 3600,
            force_refresh=force_refresh,
            timeout_seconds=20.0,
        )
        by_weekday = parse_rlublin_ramowka_html(html)
        with self._lock:
            self._week_cache = _RlublinWeekCache(expires_at=time_module.time() + 6 * 3600, by_weekday=by_weekday)
        return by_weekday


def parse_rlublin_ramowka_html(html: str) -> dict[int, list[_RlublinProgramme]]:
    soup = BeautifulSoup(html, "lxml")
    table = soup.select_one("table.tt_timetable")
    if not table:
        return {}

    out: dict[int, list[_RlublinProgramme]] = {i: [] for i in range(1, 8)}
    rowspans_left = [0] * 7

    for tr in table.select("tbody tr"):
        tds = tr.find_all("td", recursive=False)
        if not tds:
            continue
        # The first column is the time axis.
        cells = tds[1:] if len(tds) >= 2 else []
        cell_pos = 0

        col = 0
        while col < 7:
            if rowspans_left[col] > 0:
                rowspans_left[col] -= 1
                col += 1
                continue

            if cell_pos >= len(cells):
                col += 1
                continue

            cell = cells[cell_pos]
            cell_pos += 1

            rowspan = _parse_int(cell.get("rowspan"), default=1)
            colspan = _parse_int(cell.get("colspan"), default=1)
            colspan = max(1, min(colspan, 7 - col))

            for span in range(col, col + colspan):
                rowspans_left[span] = max(rowspan - 1, 0)

            programme = _parse_rlublin_event_cell(cell)
            if programme:
                out[col + 1].append(programme)

            col += colspan

    # Dedupe and sort.
    deduped: dict[int, list[_RlublinProgramme]] = {}
    for weekday, items in out.items():
        seen: set[tuple[str, str]] = set()
        uniq: list[_RlublinProgramme] = []
        for p in items:
            key = (p.start.strftime("%H:%M") if p.start else "", p.title.casefold())
            if key in seen:
                continue
            seen.add(key)
            uniq.append(p)
        uniq.sort(key=lambda p: p.start or time.min)
        deduped[weekday] = uniq

    return deduped


def _parse_rlublin_event_cell(cell) -> _RlublinProgramme | None:
    classes = cell.get("class") or []
    if "event" not in classes:
        return None

    title_el = cell.select_one(".event_header")
    title = clean_text(title_el.get_text(" ")) if title_el else ""
    if not title:
        return None

    details_ref = None
    if title_el and title_el.name == "a":
        href = clean_text(title_el.get("href") or "")
        if href:
            details_ref = urljoin(RL_BASE, href)

    hours_el = cell.select_one(".hours")
    hours = clean_text(hours_el.get_text(" ")) if hours_el else ""
    start, end = _parse_hours_range(hours)

    return _RlublinProgramme(start=start, end=end, title=title, details_ref=details_ref)


def _parse_hours_range(text: str) -> tuple[time | None, time | None]:
    m = re.match(r"^(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})$", clean_text(text))
    if not m:
        return None, None
    try:
        return parse_time_hhmm(m.group(1)), parse_time_hhmm(m.group(2))
    except Exception:  # noqa: BLE001
        return None, None


def _parse_int(value, *, default: int) -> int:
    try:
        if value is None:
            return default
        return int(str(value))
    except (TypeError, ValueError):
        return default
