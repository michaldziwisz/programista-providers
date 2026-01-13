from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, time

from bs4 import BeautifulSoup

from tvguide_app.core.http import HttpClient
from tvguide_app.core.models import ProviderId, ScheduleItem, Source, SourceId
from tvguide_app.core.providers.base import ScheduleProvider
from tvguide_app.core.util import clean_multiline_text, clean_text, parse_time_hhmm


CHOPIN_RAMOWKA_URL = "https://chopin.polskieradio.pl/ramowka"


@dataclass(frozen=True)
class _ChopinProgramme:
    start: time | None
    end: time | None
    title: str
    details: str


class PolskieRadioChopinProvider(ScheduleProvider):
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    @property
    def provider_id(self) -> str:
        return "polskieradio-chopin"

    @property
    def display_name(self) -> str:
        return "Radio Chopin (Polskie Radio)"

    def list_sources(self, *, force_refresh: bool = False) -> list[Source]:  # noqa: ARG002
        return [
            Source(
                provider_id=ProviderId(self.provider_id),
                id=SourceId("chopin"),
                name="Polskie Radio Chopin",
            )
        ]

    def list_days(self, *, force_refresh: bool = False) -> list[date]:  # noqa: ARG002
        # This page exposes only the current-day schedule (no date selector in the URL).
        return [date.today()]

    def get_schedule(
        self,
        source: Source,
        day: date,
        *,
        force_refresh: bool = False,
    ) -> list[ScheduleItem]:
        if str(source.id) != "chopin":
            return []
        if day != date.today():
            return []

        html = self._http.get_text(
            CHOPIN_RAMOWKA_URL,
            cache_key="prchopin:ramowka",
            ttl_seconds=60 * 30,
            force_refresh=force_refresh,
            timeout_seconds=20.0,
        )
        programmes = parse_pr_chopin_ramowka_html(html)
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
        return item.details_summary or item.title


def _parse_time_hhmmss(text: str) -> time | None:
    t = clean_text(text)
    if len(t) >= 5 and t[2] == ":":
        t = t[:5]
    return parse_time_hhmm(t)


def _format_hosts(hosts: list[dict]) -> str:
    names: list[str] = []
    for h in hosts:
        if not isinstance(h, dict):
            continue
        name = clean_text(str(h.get("name") or ""))
        surname = clean_text(str(h.get("surname") or ""))
        full = clean_text(" ".join([p for p in (name, surname) if p]))
        if full:
            names.append(full)
    if not names:
        return ""
    return "Prowadzą: " + ", ".join(names)


def parse_pr_chopin_ramowka_html(html: str) -> list[_ChopinProgramme]:
    if not html:
        return []

    soup = BeautifulSoup(html, "lxml")
    script = soup.find("script", id="__NEXT_DATA__")
    if not script or not script.string:
        return []

    try:
        data = json.loads(script.string)
    except json.JSONDecodeError:
        return []

    schedule = data.get("props", {}).get("pageProps", {}).get("scheduleData", [])
    if not isinstance(schedule, list):
        return []

    out: list[_ChopinProgramme] = []
    for raw in schedule:
        if not isinstance(raw, dict):
            continue

        title = clean_text(str(raw.get("title") or ""))
        if not title:
            continue

        start = _parse_time_hhmmss(str(raw.get("startTime") or ""))
        end = _parse_time_hhmmss(str(raw.get("stopTime") or ""))

        lead = clean_multiline_text(str(raw.get("lead") or ""))
        desc = clean_multiline_text(str(raw.get("description") or ""))
        current_desc = clean_multiline_text(str(raw.get("currentDescription") or ""))

        details_desc = current_desc or desc
        if lead and details_desc and lead.casefold() == details_desc.casefold():
            details_desc = ""

        hosts_raw = raw.get("hosts") or []
        hosts = _format_hosts(hosts_raw) if isinstance(hosts_raw, list) else ""

        parts = [p for p in (hosts, lead, details_desc) if p]
        details = "\n\n".join(parts)

        out.append(_ChopinProgramme(start=start, end=end, title=title, details=details))

    out.sort(key=lambda p: p.start or time.min)
    return out

