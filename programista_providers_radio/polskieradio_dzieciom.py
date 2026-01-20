from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from tvguide_app.core.http import HttpClient
from tvguide_app.core.models import ProviderId, ScheduleItem, Source, SourceId
from tvguide_app.core.providers.base import ScheduleProvider
from tvguide_app.core.util import clean_multiline_text, clean_text


PRD_SCHEDULE_API_URL = "https://apipr.polskieradio.pl/api/schedule"
PRD_PROGRAM_ID = "11"


@dataclass(frozen=True)
class _PrDzieciomProgramme:
    start: time | None
    end: time | None
    title: str
    details: str
    details_ref: str | None


class PolskieRadioDzieciomProvider(ScheduleProvider):
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    @property
    def provider_id(self) -> str:
        return "polskieradio-dzieciom"

    @property
    def display_name(self) -> str:
        return "Polskie Radio Dzieciom"

    def list_sources(self, *, force_refresh: bool = False) -> list[Source]:  # noqa: ARG002
        return [
            Source(
                provider_id=ProviderId(self.provider_id),
                id=SourceId("dzieciom"),
                name="Polskie Radio Dzieciom",
            )
        ]

    def list_days(self, *, force_refresh: bool = False) -> list[date]:  # noqa: ARG002
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
        if str(source.id) != "dzieciom":
            return []

        schedule_json = self._http.get_text(
            _build_prd_schedule_url(day),
            cache_key=f"prd:schedule:{day.isoformat()}",
            ttl_seconds=60 * 30,
            force_refresh=force_refresh,
            timeout_seconds=20.0,
        )
        programmes = parse_prd_schedule_json(schedule_json)
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
                details_summary=p.details or None,
            )
            for p in programmes
        ]

    def get_item_details(self, item: ScheduleItem, *, force_refresh: bool = False) -> str:  # noqa: ARG002
        return item.details_summary or item.title


def _build_prd_schedule_url(day: date) -> str:
    # The endpoint supports selecting day via `selectedDate=YYYY-MM-DD`.
    return f"{PRD_SCHEDULE_API_URL}?Program={PRD_PROGRAM_ID}&selectedDate={day.isoformat()}"


def parse_prd_schedule_json(text: str) -> list[_PrDzieciomProgramme]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []

    schedule = data.get("Schedule")
    if not isinstance(schedule, list):
        return []

    programmes: list[_PrDzieciomProgramme] = []
    for raw in schedule:
        if not isinstance(raw, dict):
            continue

        title = clean_text(raw.get("Title") or "")
        if not title:
            continue

        start = _parse_iso_time(raw.get("StartHour"))
        end = _parse_iso_time(raw.get("StopHour"))

        leaders = _format_leaders(raw.get("Leaders"))
        description = clean_multiline_text(raw.get("Description") or "")

        details_parts = [p for p in (leaders, description) if p]
        details = "\n\n".join(details_parts)

        details_ref = None
        programme_id = raw.get("Id")
        if isinstance(programme_id, int) or (isinstance(programme_id, str) and programme_id.isdigit()):
            details_ref = f"https://www.polskieradio.pl/18/Audycja/{programme_id}"

        programmes.append(
            _PrDzieciomProgramme(
                start=start,
                end=end,
                title=title,
                details=details,
                details_ref=details_ref,
            )
        )

    programmes.sort(key=lambda p: p.start or time.min)
    return programmes


def _parse_iso_time(value: object) -> time | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return dt.timetz().replace(tzinfo=None)


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
