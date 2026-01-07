from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time, timedelta

from bs4 import BeautifulSoup

from tvguide_app.core.http import HttpClient
from tvguide_app.core.models import ProviderId, ScheduleItem, Source, SourceId
from tvguide_app.core.providers.base import ScheduleProvider
from tvguide_app.core.util import clean_multiline_text, clean_text, parse_time_hhmm


RNS_BASE = "https://nowyswiat.online"


@dataclass(frozen=True)
class _RnsProgramme:
    start: time | None
    title: str
    details: str


class NowySwiatProvider(ScheduleProvider):
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    @property
    def provider_id(self) -> str:
        return "nowyswiat"

    @property
    def display_name(self) -> str:
        return "Radio Nowy Świat"

    def list_sources(self, *, force_refresh: bool = False) -> list[Source]:
        return [
            Source(
                provider_id=ProviderId(self.provider_id),
                id=SourceId("rns"),
                name="Radio Nowy Świat",
            )
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
        if str(source.id) != "rns":
            return []

        programmes = self._fetch_day(day, force_refresh=force_refresh)
        items: list[ScheduleItem] = []
        for p in programmes:
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
                    details_summary=p.details or None,
                )
            )
        return items

    def get_item_details(self, item: ScheduleItem, *, force_refresh: bool = False) -> str:
        return item.details_summary or item.title

    def _fetch_day(self, day: date, *, force_refresh: bool) -> list[_RnsProgramme]:
        url = f"{RNS_BASE}/ramowka?search={day.isoformat()}"
        html = self._http.get_text(
            url,
            cache_key=f"rns:ramowka:{day.isoformat()}",
            ttl_seconds=60 * 60,
            force_refresh=force_refresh,
        )
        return parse_rns_ramowka_html(html)


def parse_rns_ramowka_html(html: str) -> list[_RnsProgramme]:
    soup = BeautifulSoup(html, "lxml")
    day_container = soup.select_one("li.rns-switcher-grid-element") or soup
    out: list[_RnsProgramme] = []
    for li in day_container.select("li.rns-switcher-single"):
        time_el = li.select_one(".rns-switcher-time")
        start = parse_time_hhmm(clean_text(time_el.get_text(" "))) if time_el else None

        title_el = li.select_one(".rns-switcher-title")
        title = clean_text(title_el.get_text(" ")) if title_el else ""
        if not title:
            continue

        names_el = li.select_one(".rns-switcher-names")
        details = ""
        if names_el:
            raw = clean_multiline_text(names_el.get_text("\n"))
            lines: list[str] = []
            pending_comma = False
            for ln in [x.strip() for x in raw.splitlines()]:
                if not ln or ln == "|":
                    continue
                if ln == ",":
                    pending_comma = True
                    continue
                if ln.startswith(":") and lines:
                    lines[-1] = lines[-1].rstrip() + ln
                    pending_comma = False
                    continue
                if pending_comma and lines:
                    lines[-1] = lines[-1].rstrip() + ", " + ln
                    pending_comma = False
                    continue
                pending_comma = False
                lines.append(ln)
            details = "\n".join(lines)

        out.append(_RnsProgramme(start=start, title=title, details=details))
    return out
