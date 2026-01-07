from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time, timedelta

from bs4 import BeautifulSoup

from tvguide_app.core.http import HttpClient
from tvguide_app.core.models import ProviderId, ScheduleItem, Source, SourceId
from tvguide_app.core.providers.base import ScheduleProvider
from tvguide_app.core.util import clean_multiline_text, clean_text, parse_time_hhmm


RW_BASE = "https://www.radiowroclaw.pl"


@dataclass(frozen=True)
class _RwProgramme:
    start: time | None
    title: str
    details: str


class RadioWroclawProvider(ScheduleProvider):
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    @property
    def provider_id(self) -> str:
        return "radiowroclaw"

    @property
    def display_name(self) -> str:
        return "Radio Wrocław"

    def list_sources(self, *, force_refresh: bool = False) -> list[Source]:  # noqa: ARG002
        return [
            Source(
                provider_id=ProviderId(self.provider_id),
                id=SourceId("wroclaw"),
                name="Radio Wrocław",
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
        if str(source.id) != "wroclaw":
            return []

        weekday = day.isoweekday()  # Monday=1..Sunday=7
        html = self._http.get_text(
            f"{RW_BASE}/broadcasts/view/{weekday}",
            cache_key=f"rw:broadcasts:{weekday}",
            ttl_seconds=60 * 60 * 6,
            force_refresh=force_refresh,
            timeout_seconds=20.0,
        )
        programmes = parse_rw_broadcasts_html(html)
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


def parse_rw_broadcasts_html(html: str) -> list[_RwProgramme]:
    soup = BeautifulSoup(html, "lxml")
    table = soup.select_one("table.broadcast") or soup

    programmes: list[_RwProgramme] = []
    for row in table.select("tr.row"):
        start_el = row.select_one("td.start")
        start = parse_time_hhmm(clean_text(start_el.get_text(" "))) if start_el else None

        info = row.select_one("td.info") or row
        title_el = info.select_one("strong")
        title = clean_text(title_el.get_text(" ")) if title_el else ""
        if not title:
            continue

        raw_descs: list[str] = []
        for desc_el in info.select("div.desc"):
            desc = clean_multiline_text(desc_el.get_text("\n"))
            if desc:
                raw_descs.append(desc)

        seen_desc: set[str] = set()
        descs: list[str] = []
        for desc in raw_descs:
            key = desc.casefold()
            if key in seen_desc:
                continue
            seen_desc.add(key)
            descs.append(desc)
        details = "\n\n".join(descs)

        programmes.append(_RwProgramme(start=start, title=title, details=details))

    # Remove exact duplicates (sometimes repeated by the site).
    seen: set[tuple[str, str, str]] = set()
    out: list[_RwProgramme] = []
    for p in programmes:
        key = (p.start.strftime("%H:%M") if p.start else "", p.title.casefold(), p.details.casefold())
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out

