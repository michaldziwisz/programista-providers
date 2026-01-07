from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, time, timedelta
from typing import Any

from tvguide_app.core.http import HttpClient
from tvguide_app.core.models import ProviderId, ScheduleItem, Source, SourceId
from tvguide_app.core.providers.base import ScheduleProvider
from tvguide_app.core.util import clean_multiline_text, clean_text, parse_time_hhmm


RK_BASE = "https://radiokierowcow.pl"


@dataclass(frozen=True)
class _RkProgramme:
    start: time | None
    title: str
    lead: str
    description: str


class RadioKierowcowProvider(ScheduleProvider):
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    @property
    def provider_id(self) -> str:
        return "radiokierowcow"

    @property
    def display_name(self) -> str:
        return "Radio Kierowców"

    def list_sources(self, *, force_refresh: bool = False) -> list[Source]:
        return [
            Source(
                provider_id=ProviderId(self.provider_id),
                id=SourceId("prk"),
                name="Polskie Radio Kierowców",
            )
        ]

    def list_days(self, *, force_refresh: bool = False) -> list[date]:
        # Keep it consistent with other radio providers.
        today = date.today()
        start = today - timedelta(days=7)
        return [start + timedelta(days=i) for i in range(14)]

    def get_schedule(
        self,
        source: Source,
        day: date,
        *,
        force_refresh: bool = False,
    ) -> list[ScheduleItem]:
        if str(source.id) != "prk":
            return []

        programmes = self._get_programmes(day, force_refresh=force_refresh)
        items: list[ScheduleItem] = []
        for p in programmes:
            details = "\n\n".join([x for x in (p.lead, p.description) if x])
            items.append(
                ScheduleItem(
                    provider_id=ProviderId(self.provider_id),
                    source=source,
                    day=day,
                    start_time=p.start,
                    end_time=None,
                    title=p.title,
                    subtitle=None,
                    details_ref=None,
                    details_summary=details or None,
                )
            )
        return items

    def get_item_details(self, item: ScheduleItem, *, force_refresh: bool = False) -> str:
        # No separate details endpoint; we embed what we have in details_summary.
        return item.details_summary or item.title

    def _get_programmes(self, day: date, *, force_refresh: bool) -> list[_RkProgramme]:
        programmes = self._fetch_day(day, force_refresh=force_refresh)
        if programmes:
            return programmes

        # Some backend deployments have a limited date range; when missing, try previous years
        # by mapping to the same weekday.
        weekday = day.weekday()
        for years_back in range(1, 6):
            candidate_year = day.year - years_back
            candidate_day = _weekday_template_date(candidate_year, weekday)
            programmes = self._fetch_day(candidate_day, force_refresh=force_refresh)
            if programmes:
                return programmes
        return []

    def _fetch_day(self, day: date, *, force_refresh: bool) -> list[_RkProgramme]:
        url = f"{RK_BASE}/api/Schedule/Get?date={day.isoformat()}"
        cache_key = f"rk:schedule:{day.isoformat()}"
        text = self._http.get_text(
            url,
            cache_key=cache_key,
            ttl_seconds=60 * 30,
            force_refresh=force_refresh,
        )
        return parse_rk_schedule_json(text)


def _weekday_template_date(year: int, weekday: int) -> date:
    d = date(year, 1, 1)
    delta = (-d.weekday()) % 7
    first_monday = d + timedelta(days=delta)
    return first_monday + timedelta(days=weekday)


def _parse_time_hhmmss(text: str) -> time | None:
    t = clean_text(text)
    if len(t) >= 5 and t[2] == ":":
        t = t[:5]
    return parse_time_hhmm(t)


def parse_rk_schedule_json(text: str) -> list[_RkProgramme]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, dict):
        return []

    raw_items = data.get("data")
    if not isinstance(raw_items, list):
        return []

    programmes: list[_RkProgramme] = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        title = clean_text(str(raw.get("title") or ""))
        if not title:
            continue
        start = _parse_time_hhmmss(str(raw.get("startTime") or ""))
        lead = clean_multiline_text(str(raw.get("lead") or ""))
        desc = clean_multiline_text(str(raw.get("currentDescription") or ""))
        programmes.append(_RkProgramme(start=start, title=title, lead=lead, description=desc))
    return programmes

