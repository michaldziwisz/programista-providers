from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, time, timedelta

from bs4 import BeautifulSoup

from tvguide_app.core.http import HttpClient
from tvguide_app.core.models import ProviderId, ScheduleItem, Source, SourceId
from tvguide_app.core.providers.base import ScheduleProvider
from tvguide_app.core.util import clean_text, parse_time_hhmm


RS_BASE = "https://radioszczecin.pl"
RS_PROGRAM_DAY_URL = f"{RS_BASE}/9,0,zobacz_program"

_RS_TIME_RE = re.compile(r"\b(\d{1,2}:\d{2})\b")


@dataclass(frozen=True)
class _RsProgramme:
    start: time | None
    title: str


class RadioSzczecinProvider(ScheduleProvider):
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    @property
    def provider_id(self) -> str:
        return "radioszczecin"

    @property
    def display_name(self) -> str:
        return "Radio Szczecin"

    def list_sources(self, *, force_refresh: bool = False) -> list[Source]:  # noqa: ARG002
        return [
            Source(
                provider_id=ProviderId(self.provider_id),
                id=SourceId("radioszczecin"),
                name="Radio Szczecin",
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
        if str(source.id) != "radioszczecin":
            return []

        html = self._http.get_text(
            f"{RS_PROGRAM_DAY_URL}&dtx={day.isoformat()}",
            cache_key=f"rs:program:{day.isoformat()}",
            ttl_seconds=60 * 30,
            force_refresh=force_refresh,
            timeout_seconds=20.0,
        )

        programmes = parse_rs_program_html(html)
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
                details_summary=None,
            )
            for p in programmes
        ]

    def get_item_details(self, item: ScheduleItem, *, force_refresh: bool = False) -> str:  # noqa: ARG002
        # The site exposes detailed scenarios/playlists only for the currently active programme,
        # and loads it dynamically for others; keep it simple here.
        return item.details_summary or item.title


def _parse_time(text: str) -> time | None:
    t = clean_text(text)
    m = _RS_TIME_RE.search(t)
    if not m:
        return None
    value = m.group(1)
    if len(value) == 4:  # e.g. 0:00
        value = "0" + value
    if value.startswith("24:"):
        return None
    try:
        return parse_time_hhmm(value)
    except Exception:  # noqa: BLE001
        return None


def parse_rs_program_html(html: str) -> list[_RsProgramme]:
    soup = BeautifulSoup(html, "lxml")
    container = soup.select_one("#programdzien") or soup

    out: list[_RsProgramme] = []
    for div in container.select("div.audycja"):
        a = div.select_one("a.atytul")
        if not a:
            continue
        time_el = a.select_one("span.agodz")
        if not time_el:
            continue
        time_text = clean_text(time_el.get_text(" "))
        start = _parse_time(time_text)
        if not start:
            continue

        text = clean_text(a.get_text(" "))
        # The anchor includes the time token; strip it from the title.
        title = re.sub(rf"^\s*{re.escape(time_text)}\s*", "", text).strip()
        title = clean_text(title)
        if not title:
            continue
        out.append(_RsProgramme(start=start, title=title))

    seen: set[tuple[str, str]] = set()
    deduped: list[_RsProgramme] = []
    for it in out:
        key = (it.start.strftime("%H:%M") if it.start else "", it.title.casefold())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(it)
    return deduped
