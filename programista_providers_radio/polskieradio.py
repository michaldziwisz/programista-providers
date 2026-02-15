from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from tvguide_app.core.http import HttpClient
from tvguide_app.core.models import ProviderId, ScheduleItem, Source, SourceId
from tvguide_app.core.providers.base import ScheduleProvider
from tvguide_app.core.util import clean_multiline_text, clean_text


PR_CHANNELS: list[str] = ["Jedynka", "Dwójka", "Trójka", "Czwórka", "Radio Poland", "PR24"]

PR_SCHEDULE_API_URL = "https://apipr.polskieradio.pl/api/schedule"

# Mapping based on the official `apipr.polskieradio.pl` schedule endpoint.
PR_PROGRAM_ID_BY_CHANNEL: dict[str, str] = {
    "Jedynka": "1",
    "Dwójka": "2",
    "Trójka": "3",
    "Czwórka": "4",
    "Radio Poland": "5",
    "PR24": "6",
}


class PolskieRadioProvider(ScheduleProvider):
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    @property
    def provider_id(self) -> str:
        return "polskieradio"

    @property
    def display_name(self) -> str:
        return "Radio (Polskie Radio)"

    def list_sources(self, *, force_refresh: bool = False) -> list[Source]:
        return [
            Source(provider_id=ProviderId(self.provider_id), id=SourceId(name), name=name)
            for name in PR_CHANNELS
        ]

    def list_days(self, *, force_refresh: bool = False) -> list[date]:
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
        programme_id = PR_PROGRAM_ID_BY_CHANNEL.get(source.name)
        if not programme_id:
            return []

        schedule_json = self._http.get_text(
            _build_pr_schedule_url(programme_id, day),
            cache_key=f"pr:schedule:v2:{programme_id}:{day.isoformat()}",
            ttl_seconds=60 * 30,
            force_refresh=force_refresh,
            timeout_seconds=20.0,
        )
        items = parse_pr_schedule_json(schedule_json)
        return [
            ScheduleItem(
                provider_id=ProviderId(self.provider_id),
                source=source,
                day=day,
                start_time=item.start_time,
                end_time=item.end_time,
                title=item.title,
                subtitle=None,
                details_ref=item.details_ref,
                details_summary=item.details_summary or None,
            )
            for item in items
        ]

    def get_item_details(self, item: ScheduleItem, *, force_refresh: bool = False) -> str:
        return item.details_summary or item.title


@dataclass(frozen=True)
class _PrItem:
    start_time: time | None
    end_time: time | None
    title: str
    details_ref: str | None
    details_summary: str


def _build_pr_schedule_url(programme_id: str, day: date) -> str:
    return f"{PR_SCHEDULE_API_URL}?Program={programme_id}&selectedDate={day.isoformat()}"


def parse_pr_schedule_json(text: str) -> list[_PrItem]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []

    schedule = data.get("Schedule")
    if not isinstance(schedule, list):
        return []

    parsed: list[tuple[datetime | None, _PrItem]] = []
    for raw in schedule:
        if not isinstance(raw, dict):
            continue

        title = clean_text(raw.get("Title") or "")
        if not title:
            continue

        start_dt = _parse_iso_datetime(raw.get("StartHour"))
        end_dt = _parse_iso_datetime(raw.get("StopHour"))

        start = start_dt.timetz().replace(tzinfo=None) if start_dt else None
        end = end_dt.timetz().replace(tzinfo=None) if end_dt else None

        leaders = _format_leaders(raw.get("Leaders"))
        description = clean_multiline_text(raw.get("Description") or "")
        details_parts = [p for p in (leaders, description) if p]
        details = "\n\n".join(details_parts)

        details_ref = _normalize_url(raw.get("ArticleLink"))

        parsed.append((start_dt, _PrItem(start_time=start, end_time=end, title=title, details_ref=details_ref, details_summary=details)))

    parsed.sort(key=lambda x: x[0] or datetime.min)

    seen: set[tuple[str, str]] = set()
    out: list[_PrItem] = []
    for _, item in parsed:
        key = (item.start_time.strftime("%H:%M") if item.start_time else "", item.title.casefold())
        if key in seen:
            continue
        seen.add(key)
        out.append(item)

    return out


def _parse_iso_datetime(value: object) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _format_leaders(value: object) -> str:
    if not isinstance(value, list):
        return ""
    names: list[str] = []
    for leader in value:
        if not isinstance(leader, dict):
            continue
        first = clean_text(leader.get("Name") or "")
        last = clean_text(leader.get("SurName") or "")
        full = clean_text(" ".join([p for p in (first, last) if p]))
        if full:
            names.append(full)
    if not names:
        return ""
    # Keep the original order while removing duplicates case-insensitively.
    seen: set[str] = set()
    uniq: list[str] = []
    for name in names:
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        uniq.append(name)
    return f"Prowadzący: {', '.join(uniq)}"


def _normalize_url(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    url = clean_text(value)
    if not url:
        return None
    if url.startswith("//"):
        return f"https:{url}"
    return url
