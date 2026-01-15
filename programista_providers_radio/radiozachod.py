from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, time, timedelta
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from tvguide_app.core.http import HttpClient
from tvguide_app.core.models import ProviderId, ScheduleItem, Source, SourceId
from tvguide_app.core.providers.base import ScheduleProvider
from tvguide_app.core.util import clean_text, parse_time_hhmm


RZ_BASE = "https://zachod.pl"
RZ_AJAX = f"{RZ_BASE}/wp-admin/admin-ajax.php"

_RZ_TIME_RE = re.compile(r"\b(\d{1,2}:\d{2})\b")


@dataclass(frozen=True)
class _RzProgramme:
    start: time | None
    end: time | None
    title: str


class RadioZachodProvider(ScheduleProvider):
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    @property
    def provider_id(self) -> str:
        return "radiozachod"

    @property
    def display_name(self) -> str:
        return "Radio Zachód"

    def list_sources(self, *, force_refresh: bool = False) -> list[Source]:  # noqa: ARG002
        return [
            Source(
                provider_id=ProviderId(self.provider_id),
                id=SourceId("radiozachod"),
                name="Radio Zachód",
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
        if str(source.id) != "radiozachod":
            return []

        # The schedule endpoint renders a whole week (Mon-Sun) containing `start_date`.
        # Use the week's Monday to keep network/cache stable across days.
        week_start = day - timedelta(days=day.weekday())
        url = _build_schedule_url(week_start=week_start)

        html = self._http.get_text(
            url,
            cache_key=f"rz:ramowka:week:{week_start.isoformat()}",
            ttl_seconds=60 * 30,
            force_refresh=force_refresh,
            timeout_seconds=20.0,
        )

        programmes = parse_rz_ramowka_html(html, day)
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
                details_summary=None,
            )
            for p in programmes
        ]

    def get_item_details(self, item: ScheduleItem, *, force_refresh: bool = False) -> str:  # noqa: ARG002
        return item.details_summary or item.title


def _build_schedule_url(*, week_start: date) -> str:
    # Minimal set of params needed for a stable HTML response.
    params = {
        "action": "radio_station_schedule",
        "view": "table",
        "start_date": week_start.isoformat(),
        "active_date": week_start.isoformat(),
        "timezone": "1",
        "time": "24",
        "show_times": "1",
        "show_link": "1",
        "show_encore": "1",
    }
    return f"{RZ_AJAX}?{urlencode(params)}"


def _parse_time_token(value: str) -> time | None:
    t = clean_text(value)
    m = _RZ_TIME_RE.search(t)
    if not m:
        return None
    hhmm = m.group(1)
    if len(hhmm) == 4 and hhmm[1] == ":":  # e.g. 0:00
        hhmm = "0" + hhmm
    if hhmm.startswith("24:"):
        return None
    try:
        return parse_time_hhmm(hhmm)
    except Exception:  # noqa: BLE001
        return None


def parse_rz_ramowka_html(html: str, day: date) -> list[_RzProgramme]:
    soup = BeautifulSoup(html, "lxml")
    table = soup.select_one("#master-program-schedule") or soup

    day_cls = f"date-{day.isoformat()}"
    out: list[_RzProgramme] = []
    for entry in table.select(f"td.show-info.{day_cls} div.master-show-entry.newshift"):
        title_el = entry.select_one(".show-title")
        title = clean_text(title_el.get_text(" ")) if title_el else ""
        if not title:
            continue

        start_el = entry.select_one(".show-time .rs-start-time")
        end_el = entry.select_one(".show-time .rs-end-time")
        start = _parse_time_token(start_el.get_text(" ")) if start_el else None
        end = _parse_time_token(end_el.get_text(" ")) if end_el else None

        out.append(_RzProgramme(start=start, end=end, title=title))

    seen: set[tuple[str, str]] = set()
    deduped: list[_RzProgramme] = []
    for it in out:
        start_key = it.start.strftime("%H:%M") if it.start else ""
        key = (start_key, it.title.casefold())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(it)
    return deduped

